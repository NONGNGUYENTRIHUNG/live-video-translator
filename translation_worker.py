"""Local CPU translation worker. Standard output is reserved for JSON responses."""
import sys
import json
import traceback
from collections import OrderedDict
from translation_models import MODEL_ID,route,split_to_fit
wire=sys.stdout
sys.stdout=sys.stderr

def send(**message):
    wire.write(json.dumps(message,ensure_ascii=True)+'\n'); wire.flush()

def main():
    import torch
    from transformers import AutoTokenizer,AutoModelForSeq2SeqLM
    torch.set_num_threads(3)
    cache=OrderedDict()
    def load(model_id,request_id):
        if model_id in cache:
            cache.move_to_end(model_id); return cache[model_id]
        send(id=request_id,kind='status',message='Loading local translation model: '+model_id)
        if len(cache)>=2: cache.popitem(last=False)
        tokenizer=AutoTokenizer.from_pretrained(model_id)
        model=AutoModelForSeq2SeqLM.from_pretrained(model_id).eval().to('cpu')
        cache[model_id]=(tokenizer,model)
        return tokenizer,model
    send(id=0,kind='ready')
    for line in sys.stdin:
        request=json.loads(line)
        if request['op']=='close': break
        ident=request['id']
        try:
            source,target=request['source'],request['target']
            model_id=route(source,target)
            if model_id is None:
                send(id=ident,kind='result',text=request.get('text',''),model='passthrough'); continue
            tokenizer,model=load(model_id,ident)
            if request['op']=='prepare':
                send(id=ident,kind='result',text='',model=model_id); continue
            options={}
            if model_id==MODEL_ID:
                if source not in tokenizer.lang_code_to_id or target not in tokenizer.lang_code_to_id:
                    raise ValueError(f'Translation model does not support {source} -> {target}. Select the source language explicitly.')
                tokenizer.src_lang=source
                options['forced_bos_token_id']=tokenizer.get_lang_id(target)
            results=[]
            for part in split_to_fit(request['text'],tokenizer):
                inputs=tokenizer(part,return_tensors='pt',truncation=False)
                with torch.inference_mode():
                    output=model.generate(**inputs,num_beams=4,do_sample=False,max_new_tokens=512,**options)
                if output.shape[-1] >= 513 or int(output[0,-1])!=model.config.eos_token_id:
                    raise RuntimeError('Translation reached its output limit; refusing to show a cut-off sentence.')
                results.append(tokenizer.decode(output[0],skip_special_tokens=True).strip())
            send(id=ident,kind='result',text=' '.join(results),model=model_id)
        except Exception as exc:
            traceback.print_exc(); send(id=ident,kind='error',message=str(exc))

if __name__=='__main__':
    try: main()
    except Exception as exc:
        traceback.print_exc(); send(id=0,kind='fatal',message=str(exc))
