from typing import List, Dict
import re

def clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)       # collapse whitespace
    text = re.sub(r'\n{3,}', '\n\n', text) # max 2 newlines
    return text.strip()

def recursive_character_text_splitter(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[str]:
    """
    Simple recursive character text splitter.
    Splits text by double newlines, then single newlines, then spaces.
    """
    # A simplified implementation for the structure.
    # In production, using LangChain's RecursiveCharacterTextSplitter is recommended.
    
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + chunk_size
        if end >= text_length:
            chunks.append(text[start:text_length])
            break
            
        # Try to find a good breaking point
        break_point = end
        for separator in ["\n\n", "\n", ". ", " "]:
            sep_idx = text.rfind(separator, start, end)
            if sep_idx != -1:
                break_point = sep_idx + len(separator)
                break
                
        chunks.append(text[start:break_point].strip())
        start = break_point - chunk_overlap
        
    return chunks

def chunk_document(pages: List[Dict[str, any]]) -> List[Dict[str, any]]:
    """
    Takes a list of pages (dict with 'page_number' and 'text') and returns chunks
    preserving the page number metadata.
    """
    document_chunks = []
    
    for page in pages:
        text_chunks = recursive_character_text_splitter(page['text'])
        for chunk in text_chunks:
            if chunk: # ignore empty
                document_chunks.append({
                    "text": chunk,
                    "page_number": page['page_number']
                })
                
    return document_chunks

def sample_document_text(full_text: str, max_chars: int = 12000) -> str:
    """
    Instead of truncating to first N chars, take samples from
    beginning (50%), middle (25%), and end (25%) of the document.
    This gives the LLM a representative view of the full content.
    """
    n = len(full_text)
    if n <= max_chars:
        return full_text
    
    part_a = full_text[:max_chars // 2]                          # first 50%
    part_b = full_text[n//2 - max_chars//8 : n//2 + max_chars//8]  # middle 25%
    part_c = full_text[-(max_chars // 4):]                      # last 25%
    
    return f"{part_a}\n\n[...middle excerpt...]\n\n{part_b}\n\n[...end excerpt...]\n\n{part_c}"
