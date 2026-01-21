from web.supabase_client import get_client, get_all_branch_summaries, update_branch_summary_field

def populate_keywords():
    client = get_client()
    
    # 1. Get all summaries
    print("Fetching all summaries...")
    summaries = get_all_branch_summaries(limit=1000)
    print(f"Found {len(summaries)} summaries.")
    
    updated_count = 0
    
    for s in summaries:
        branch_id = s['branch_id']
        
        # 2. Get top tags for this branch (period_type='all')
        # We need to join with tags table to get names
        tags_result = client.table('branch_tags').select(
            'tag_id, count, tags(name)'
        ).eq('branch_id', branch_id).eq('period_type', 'all').order('count', desc=True).limit(3).execute()
        
        tags = tags_result.data
        if not tags:
            # Try without period_type if 'all' is missing, or just skip
            tags_result = client.table('branch_tags').select(
                'tag_id, count, tags(name)'
            ).eq('branch_id', branch_id).order('count', desc=True).limit(3).execute()
            tags = tags_result.data
            
        if tags:
            keywords = [t['tags']['name'] for t in tags if t.get('tags')]
            
            # Update summary
            data = {}
            if len(keywords) > 0: data['keyword_1'] = keywords[0]
            if len(keywords) > 1: data['keyword_2'] = keywords[1]
            if len(keywords) > 2: data['keyword_3'] = keywords[2]
            
            if data:
                print(f"Updating branch {branch_id} with keywords: {keywords}")
                client.table('branch_summaries').update(data).eq('branch_id', branch_id).execute()
                updated_count += 1
                
    print(f"Updated {updated_count} summaries.")

if __name__ == "__main__":
    populate_keywords()
