"""One multilingual translation engine; no language-pair-specific routing."""
MODEL_ID='facebook/m2m100_418M'

def route(source,target):
    return None if source==target else MODEL_ID

def split_to_fit(text, tokenizer, max_tokens=440):
    """Never silently truncate input; prefer sentence/clause breaks when splitting."""
    import re
    if len(tokenizer.encode(text,add_special_tokens=True))<=max_tokens: return [text]
    candidates=[m.end() for m in re.finditer(r'[.!?;,]\s+|\s+',text)]
    middle=len(text)//2
    split=min(candidates,key=lambda x:abs(x-middle)) if candidates else middle
    if not split or split>=len(text): raise ValueError('Translation input cannot be split safely.')
    left,right=text[:split].strip(),text[split:].strip()
    return split_to_fit(left,tokenizer,max_tokens)+split_to_fit(right,tokenizer,max_tokens)
