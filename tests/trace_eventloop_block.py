"""이벤트 루프 블로킹 진단 스크립트

sync_reviews() 호출 체인 내부에 trace를 삽입하여
정확히 어느 지점에서 이벤트 루프가 멈추는지 찾는다.

방법:
1. sync_service.sync_reviews, _process_day_chunk, pipeline.run을 monkey-patch
2. 각 주요 지점에서 print("[TRACE] ...") 출력
3. 별도 스레드에서 서버를 시작하고, 메인 스레드에서 sync 트리거 + 폴링
4. 폴 응답 시간과 trace 순서를 비교하여 블로킹 지점 특정
"""

import asyncio
import sys
import time
import threading
from pathlib import Path

# 프로젝트 경로 설정
APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

import requests

# ============================================================
# 1) Monkey-patch: sync_service.sync_reviews에 trace 삽입
# ============================================================
_T0 = None

def trace(label: str):
    global _T0
    if _T0 is None:
        _T0 = time.monotonic()
    elapsed = time.monotonic() - _T0
    print(f"[TRACE] {elapsed:8.1f}s | {label}", flush=True)


def install_traces():
    """sync_reviews, _process_day_chunk, pipeline.run에 trace 삽입"""

    # --- sync_service.sync_reviews ---
    from services import sync_service as ss_mod

    _orig_sync_reviews = ss_mod.SyncService.sync_reviews

    async def _traced_sync_reviews(self, *args, **kwargs):
        trace("sync_reviews START")

        # 내부 분기를 추적하기 위해 원본 메서드의 핵심 부분을 직접 실행
        from core.timezone import utc_now
        from datetime import timedelta, datetime
        from repository.database import get_session_factory
        from repository.sync_metadata_repository import SyncMetadataRepository
        from schemas.sync import SyncResultResponse
        import gc

        start_time = utc_now()
        progress_callback = kwargs.get("progress_callback") or (args[0] if args else None)
        date_from = kwargs.get("date_from") or (args[1] if len(args) > 1 else None)
        date_to = kwargs.get("date_to") or (args[2] if len(args) > 2 else None)

        if not self._athena_client:
            trace("sync_reviews: no athena client")
            return SyncResultResponse(success=False, message="Athena 클라이언트 없음", error="no_athena")

        trace("sync_reviews: before get_session_factory")
        session = get_session_factory()()
        trace("sync_reviews: session created")

        try:
            metadata_repo = SyncMetadataRepository(session)

            trace("sync_reviews: before get_last_sync_at (첫 await)")
            if date_from:
                since = datetime.strptime(date_from, "%Y-%m-%d")
                trace(f"sync_reviews: date_from parsed: {since}")
            else:
                since = await metadata_repo.get_last_sync_at(ss_mod.SYNC_TYPE)
                trace(f"sync_reviews: get_last_sync_at returned: {since}")
                if not since:
                    since = utc_now() - timedelta(days=7)

            until = None
            if date_to:
                until = datetime.strptime(date_to + " 23:59:59", "%Y-%m-%d %H:%M:%S")

            day_ranges = ss_mod._generate_day_ranges(since, until)
            total_days = len(day_ranges)
            trace(f"sync_reviews: {total_days} day chunks generated")

            if progress_callback:
                await progress_callback(5, f"동기화 시작 ({total_days}일)")

            total_synced = total_new = total_processed = 0
            chunk_errors = []

            for day_idx, (chunk_since, chunk_until) in enumerate(day_ranges):
                trace(f"sync_reviews: chunk {day_idx+1}/{total_days} START")
                try:
                    synced, new, processed = await self._process_day_chunk(
                        chunk_since, chunk_until, day_idx, total_days, progress_callback,
                    )
                    total_synced += synced
                    total_new += new
                    total_processed += processed
                    trace(f"sync_reviews: chunk {day_idx+1} DONE (synced={synced})")
                except Exception as e:
                    trace(f"sync_reviews: chunk {day_idx+1} FAILED: {e}")
                    chunk_errors.append(str(e))

            trace("sync_reviews: all chunks done, updating metadata")
            if progress_callback:
                await progress_callback(95, "메타데이터 업데이트")
            await metadata_repo.update_last_sync_at(ss_mod.SYNC_TYPE)
            await session.commit()
            trace("sync_reviews: commit done")

            duration = (utc_now() - start_time).total_seconds()
            return SyncResultResponse(
                success=True,
                message=f"{total_synced}개 저장 + {total_processed}개 분석",
                synced_count=total_synced,
                new_reviews=total_new,
                duration_seconds=duration,
            )
        except Exception as e:
            trace(f"sync_reviews: EXCEPTION: {e}")
            return SyncResultResponse(
                success=False, message="동기화 실패", error=str(e),
                duration_seconds=(utc_now() - start_time).total_seconds(),
            )
        finally:
            await session.close()
            trace("sync_reviews: session closed")

    ss_mod.SyncService.sync_reviews = _traced_sync_reviews

    # --- sync_service._process_day_chunk ---
    _orig_process_day_chunk = ss_mod.SyncService._process_day_chunk

    async def _traced_process_day_chunk(self, chunk_since, chunk_until, day_idx, total_days, progress_callback):
        day_label = chunk_since.strftime("%m-%d")
        trace(f"  chunk[{day_label}]: before athena fetch (to_thread)")
        athena_reviews = await asyncio.to_thread(
            self._athena_client.fetch_reviews_since,
            chunk_since, until=chunk_until,
        )
        trace(f"  chunk[{day_label}]: athena returned {len(athena_reviews) if athena_reviews else 0} reviews")

        if not athena_reviews:
            return 0, 0, 0

        # dedup
        seen_ids = set()
        reviews = []
        for row in athena_reviews:
            rid = row.get("review_id")
            if rid not in seen_ids:
                seen_ids.add(rid)
                reviews.append(row)
        del athena_reviews, seen_ids
        import gc; gc.collect()

        trace(f"  chunk[{day_label}]: before count_existing_review_ids")
        review_ids = []
        for r in reviews:
            raw = r.get("review_id") or r.get("리뷰번호")
            if raw is not None:
                try:
                    review_ids.append(int(raw))
                except (ValueError, TypeError):
                    pass
        existing_count = await self._review_repo.count_existing_review_ids(review_ids)
        trace(f"  chunk[{day_label}]: existing_count={existing_count}")

        for row in reviews:
            row["is_new"] = True

        trace(f"  chunk[{day_label}]: before upsert_batch ({len(reviews)} reviews)")
        saved_count = await self._review_repo.upsert_batch(reviews)
        trace(f"  chunk[{day_label}]: upsert done, saved={saved_count}")

        new_count = max(saved_count - existing_count, 0)
        await self._review_repo.commit()
        trace(f"  chunk[{day_label}]: commit done")

        trace(f"  chunk[{day_label}]: before pipeline.run ({len(reviews)} reviews)")
        chunk_cb = ss_mod._make_chunk_callback(progress_callback, day_idx, total_days)
        result = await self._pipeline.run(reviews, chunk_cb)
        trace(f"  chunk[{day_label}]: pipeline.run DONE (processed={result.processed_reviews})")

        del reviews
        gc.collect()
        return saved_count, new_count, result.processed_reviews

    ss_mod.SyncService._process_day_chunk = _traced_process_day_chunk

    # --- unified_pipeline.run ---
    from domain.pipeline import unified_pipeline as up_mod

    _orig_pipeline_run = up_mod.UnifiedPipeline.run

    async def _traced_pipeline_run(self, reviews, progress_callback=None):
        trace("    pipeline.run START")

        from repository.database import get_session_factory
        factory = get_session_factory()
        trace("    pipeline: before session create")
        session = factory()
        trace("    pipeline: session created")

        try:
            # Step 1: preprocessor (GIL 의심 지점!)
            trace("    pipeline Step1: before to_thread(process_batch)")
            t0 = time.monotonic()
            processed = await asyncio.to_thread(
                self.preprocessor.process_batch, reviews
            )
            dt = time.monotonic() - t0
            trace(f"    pipeline Step1: DONE ({dt:.1f}s, {len(processed)} processed)")

            if not processed:
                from core.timezone import utc_now
                from schemas.dto import PipelineResultDTO
                r = PipelineResultDTO(
                    success=True, total_reviews=len(reviews),
                    processed_reviews=0, total_branches=0,
                    summaries_generated=0, started_at=utc_now(), finished_at=utc_now(),
                )
                await session.close()
                return r

            reviews.clear()
            import gc; gc.collect()
            if progress_callback:
                await progress_callback(50, "전처리 완료")

            # Steps 2-9 (DB 작업들)
            step_names = [
                ("review_updater", self.review_updater, "update"),
                ("tag_aggregator", self.tag_aggregator, "aggregate"),
                ("car_model_tags", self.car_model_tags, "aggregate"),
                ("keyword_manager", self.keyword_manager, "update"),
                ("review_tag_mapper", self.review_tag_mapper, "save"),
                ("monthly_stats", self.monthly_stats, "update"),
                ("monthly_car_model_stats", self.monthly_car_model_stats, "update"),
            ]

            for i, (name, step, method_name) in enumerate(step_names, start=2):
                trace(f"    pipeline Step{i}: {name} START")
                t0 = time.monotonic()
                try:
                    async with session.begin_nested():
                        method = getattr(step, method_name)
                        await method(session, processed)
                    dt = time.monotonic() - t0
                    trace(f"    pipeline Step{i}: {name} DONE ({dt:.1f}s)")
                except Exception as e:
                    dt = time.monotonic() - t0
                    trace(f"    pipeline Step{i}: {name} FAILED ({dt:.1f}s) {e}")

            await session.commit()
            trace("    pipeline: commit done")

        except Exception as e:
            await session.rollback()
            trace(f"    pipeline: EXCEPTION: {e}")
            raise
        finally:
            await session.close()

        from core.timezone import utc_now
        from schemas.dto import PipelineResultDTO
        branch_ids = {pr.branch_id for pr in processed}
        r = PipelineResultDTO(
            success=True, total_reviews=len(processed) + len(reviews),
            processed_reviews=len(processed), total_branches=len(branch_ids),
            summaries_generated=0, started_at=utc_now(), finished_at=utc_now(),
        )
        trace("    pipeline.run END")
        return r

    up_mod.UnifiedPipeline.run = _traced_pipeline_run

    # --- sync_job_service._run_job trace ---
    from services import sync_job_service as sjs_mod

    _orig_run_job = sjs_mod.SyncJobService._run_job

    async def _traced_run_job(self, state, date_from=None, date_to=None):
        global _T0
        _T0 = time.monotonic()
        trace("_run_job START")
        trace("_run_job: setting status=processing")
        state.status = "processing"
        state.progress = 0
        state.message = "동기화 준비 중"
        try:
            async def progress_callback(progress, message):
                state.progress = progress
                state.message = message
                trace(f"_run_job: progress={progress} msg={message}")

            from repository.database import get_session_factory
            from repository.review_repository import BranchReviewRepository

            trace("_run_job: before get_session_factory")
            session = get_session_factory()()
            trace("_run_job: session created")

            try:
                review_repo = BranchReviewRepository(session)
                trace("_run_job: before _create_sync_service (to_thread)")

                def _create_sync_service():
                    trace("  _create_sync_service START (in thread)")
                    from core.container import ServiceContainer
                    from services.sync_service import SyncService
                    athena_client = ServiceContainer.get_athena_client()
                    trace("  _create_sync_service: athena_client created")
                    svc = SyncService(review_repo, athena_client)
                    trace("  _create_sync_service DONE")
                    return svc

                sync_service = await asyncio.to_thread(_create_sync_service)
                trace("_run_job: to_thread returned, calling sync_reviews")

                result = await sync_service.sync_reviews(
                    progress_callback=progress_callback,
                    date_from=date_from,
                    date_to=date_to,
                )
                trace("_run_job: sync_reviews returned")
                await session.commit()
                trace("_run_job: session commit done")
                import gc; gc.collect()
            except Exception as e:
                trace(f"_run_job: EXCEPTION in sync: {e}")
                await session.rollback()
                raise
            finally:
                await session.close()
                trace("_run_job: session closed")

            state.status = "completed"
            state.progress = 100
            state.message = result.message
            state.result = result
            trace("_run_job: COMPLETED")

        except asyncio.CancelledError:
            state.status = "failed"
            state.error = "작업이 취소되었습니다"
            trace("_run_job: CANCELLED")
        except BaseException as e:
            state.status = "failed"
            state.error = str(e)
            state.message = "동기화 중 오류 발생"
            trace(f"_run_job: FAILED: {e}")

    sjs_mod.SyncJobService._run_job = _traced_run_job


# ============================================================
# 2) 이벤트 루프 응답성 모니터링
# ============================================================
def poll_loop(base_url: str, stop_event: threading.Event):
    """별도 스레드에서 2초마다 status 폴링 — 응답 시간 측정"""
    poll_num = 0
    job_id = None

    # sync 시작
    trace("POLL: triggering sync...")
    try:
        resp = requests.post(f"{base_url}/api/sync/start", timeout=10)
        data = resp.json()
        job_id = data.get("data", {}).get("job_id") or data.get("job_id")
        trace(f"POLL: sync triggered, job_id={job_id}, status={resp.status_code}")
    except Exception as e:
        trace(f"POLL: sync trigger FAILED: {e}")
        return

    if not job_id:
        trace("POLL: no job_id, aborting")
        return

    while not stop_event.is_set() and poll_num < 120:
        time.sleep(2)
        poll_num += 1
        t_start = time.monotonic()
        try:
            resp = requests.get(f"{base_url}/api/sync/status/{job_id}", timeout=5)
            dt = time.monotonic() - t_start
            data = resp.json()
            status = data.get("data", {}).get("status") or data.get("status", "?")
            progress = data.get("data", {}).get("progress") or data.get("progress", "?")
            trace(f"POLL #{poll_num}: {dt:.2f}s | status={status} progress={progress}")

            if status in ("completed", "failed"):
                trace(f"POLL: job finished ({status})")
                break
        except requests.Timeout:
            dt = time.monotonic() - t_start
            trace(f"POLL #{poll_num}: TIMEOUT ({dt:.1f}s) ← EVENT LOOP BLOCKED!")
        except Exception as e:
            dt = time.monotonic() - t_start
            trace(f"POLL #{poll_num}: ERROR ({dt:.1f}s): {e}")

    stop_event.set()


# ============================================================
# 3) 메인: uvicorn 서버 시작 + 폴링
# ============================================================
def main():
    import uvicorn

    # monkey-patch 설치
    install_traces()

    # 서버 시작 (별도 스레드)
    PORT = 18770
    config = uvicorn.Config("main:app", host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # 서버 준비 대기
    base_url = f"http://127.0.0.1:{PORT}"
    for _ in range(30):
        try:
            requests.get(f"{base_url}/docs", timeout=2)
            trace("SERVER READY")
            break
        except Exception:
            time.sleep(1)
    else:
        print("서버 시작 실패")
        return

    # 폴링 시작
    stop = threading.Event()
    try:
        poll_loop(base_url, stop)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.should_exit = True
        print("\n===== TRACE COMPLETE =====")


if __name__ == "__main__":
    main()
