
import os

FILE_PATH = 'web/templates/dashboard_v2.html'

NEW_FUNC = """        // Helper: Render stars
        function getStarRating(rating) {
            if (rating === undefined || rating === null) return '-';
            const numRating = Number(rating);
            if (isNaN(numRating)) return '-';
            
            const fullStars = Math.floor(numRating);
            const hasHalfStar = numRating % 1 >= 0.5;
            let html = '<div class="rating" style="display:inline-flex; align-items:center;">';
            
            for (let i = 0; i < 5; i++) {
                if (i < fullStars) {
                    html += '<span class="rating-star" style="color:#F59E0B;">★</span>';
                } else if (i === fullStars && hasHalfStar) {
                    html += '<span class="rating-star" style="background: linear-gradient(90deg, #F59E0B 50%, #DDDDDD 50%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">★</span>';
                } else {
                    html += '<span class="rating-star" style="color:#DDDDDD;">★</span>';
                }
            }
            html += `<span style="margin-left: 4px; color: var(--grey-4); font-weight: normal; font-size: 12px;">(${numRating.toFixed(1)})</span>`;
            html += '</div>';
            return html;
        }"""

def update_file():
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Identifying the start and end of the function to replace is tricky with just string matching if we don't have exact match.
    # But we know the header "function getStarRating(rating) {" and the end of it.
    # Actually, the file content view showed exact previous content. 
    # Let's try to just find the function signature and replace until the end of the function block.
    # However, since I had trouble matching the block before, I should be careful.
    
    # Let's try to locate the specific unique lines.
    start_marker = "function getStarRating(rating) {"
    end_marker = "return html;\n        }"
    
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print("Could not find start marker")
        return

    # Find the closing brace of the function. We can just scan for "return html;"
    # and the next closing brace.
    end_idx = content.find(end_marker, start_idx)
    if end_idx == -1:
        # try without newline
        end_marker = "return html;\n        }" # assuming formatting
        # Let's look for the next "}" after return html;
        ret_idx = content.find("return html;", start_idx)
        if ret_idx != -1:
             brace_idx = content.find("}", ret_idx)
             end_idx = brace_idx + 1
        else:
             print("Could not find return html;")
             return
            
    if end_idx != -1:
        # We need to capture the indentation before start_marker potentially?
        # The replacement string includes indentation.
        
        # We replace from start_idx - indentation?
        # My string starts with spaces.
        # Let's check matching previous content exactly.
        
        # Previous known content snippet
        old_snippet = "html += '<span class=\"rating-star\" style=\"opacity: 0.3;\">★</span>';"
        if old_snippet not in content:
             print("Warning: Old snippet not found, maybe file changed?")
        else:
             print("Old snippet found.")

        # Let's search for the block
        # I'll rely on the start marker and replacing the entire block carefully.
        # Ideally I should use regex but I'll try simple string replacement of the known buggy block.
        
        # I will construct the OLD block from what I saw in view_file.
        old_block_part = """            for (let i = 0; i < 5; i++) {
                if (i < fullStars) {
                    html += '<span class="rating-star">★</span>';
                } else if (i === fullStars && hasHalfStar) {
                    html += '<span class="rating-star" style="position: relative; overflow: hidden; display: inline-block; width: 0.5em; vertical-align: bottom;">★</span><span style="opacity: 0.3; margin-left: -0.5em;">★</span>';
                } else {
                    html += '<span class="rating-star" style="opacity: 0.3;">★</span>';
                }
            }
            html += `<span style="margin-left: 4px; color: var(--grey-4); font-weight: normal; font-size: 12px;">(${rating.toFixed(1)})</span>`;"""
            
        if old_block_part in content:
             print("Exact old block found. Replacing...")
             # Reconstruct full old block to be safe or just replace this inner part?
             # Replacing inner part allows me to keep the wrapper.
             
             new_inner_part = """            for (let i = 0; i < 5; i++) {
                if (i < fullStars) {
                    html += '<span class="rating-star" style="color:#F59E0B;">★</span>';
                } else if (i === fullStars && hasHalfStar) {
                    html += '<span class="rating-star" style="background: linear-gradient(90deg, #F59E0B 50%, #DDDDDD 50%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">★</span>';
                } else {
                    html += '<span class="rating-star" style="color:#DDDDDD;">★</span>';
                }
            }
            html += `<span style="margin-left: 4px; color: var(--grey-4); font-weight: normal; font-size: 12px;">(${numRating.toFixed(1)})</span>`;"""
            
             new_content = content.replace(old_block_part, new_inner_part)
             
             # Also need to fix the variable name usage (rating vs numRating).
             # In old block I see `(${rating.toFixed(1)})`
             # In new block I use `numRating`.
             # So I need to ensure `const numRating = Number(rating);` is also present or added.
             
             # The old block has `const fullStars = Math.floor(rating);` (wait, verify)
             # View file said: `const fullStars = Math.floor(rating);`
             # New block expects `const fullStars = Math.floor(numRating);`
             
             # Okay, better to replace the WHOLE function.
             pass

    # Safe fallback: Replace the whole function body from signature to end.
    # Find start
    s_idx = content.find("function getStarRating(rating) {")
    if s_idx == -1:
        print("Func not found")
        return
        
    # Find end (end of file or next function?)
    # The next function is `function renderTable(data)`
    e_idx = content.find("function renderTable(data)", s_idx)
    if e_idx == -1:
         print("Next func not found")
         return
    
    # We want to replace everything between s_idx and e_idx with NEW_FUNC + \n\n
    # Need to match indentation of renderTable which is 8 spaces.
    
    # Check what is between s_idx and e_idx.
    # It should look like the old function.
    
    # Let's do the replacement.
    prefix = content[:s_idx]
    suffix = content[e_idx:]
    
    # There is usually some whitespace/comments between functions.
    # My NEW_FUNC has indentation included.
    
    final_content = prefix + NEW_FUNC + "\n\n        " + suffix.lstrip() 
    # lstrip suffix to remove extra newlines/spaces before renderTable if any?
    # Actually, suffix starts with "function renderTable...".
    # I added "\n\n        " to separate.
    
    # Write back
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(final_content)
    print("Successfully updated file.")

if __name__ == "__main__":
    update_file()
