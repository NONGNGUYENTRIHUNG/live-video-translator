"""Antialiased rounded ttk surfaces, retaining native keyboard/button behavior."""
import tkinter as tk

def surface(master, fill, outside, border, radius=12, size=40):
    rgb=lambda h: tuple(int(h[i:i+2],16) for i in (1,3,5))
    colors=list(map(rgb,(outside,border,fill)))
    def inside(x,y,inset):
        r=max(0,radius-inset)
        if not inset<=x<size-inset or not inset<=y<size-inset: return False
        cx=min(max(x,inset+r),size-inset-r)
        cy=min(max(y,inset+r),size-inset-r)
        return (x-cx)**2+(y-cy)**2<=r*r
    rows=[]
    for y in range(size):
        row=[]
        for x in range(size):
            total=[0,0,0]
            for dy in (.125,.375,.625,.875):
                for dx in (.125,.375,.625,.875):
                    index=2 if inside(x+dx,y+dy,1) else 1 if inside(x+dx,y+dy,0) else 0
                    for c in range(3): total[c]+=colors[index][c]
            row.append('#%02x%02x%02x'%tuple(round(c/16) for c in total))
        rows.append('{'+' '.join(row)+'}')
    image=tk.PhotoImage(master=master,width=size,height=size)
    image.put(' '.join(rows))
    return image

def install(ui,p):
    s=ui.style
    if not hasattr(ui,'rounded_cache'): ui.rounded_cache={}
    key=ui.theme.get()
    if key not in ui.rounded_cache:
        prefix='Gold' if key=='Dark & Gold' else 'Blue'
        images=[]
        elements={}
        for style,fill in [('TButton',p['panel']),('Accent.TButton',p['accent']),('Card.TFrame',p['panel']),('TCombobox',p['panel'])]:
            element=prefix+style.replace('.','')+'.rounded'
            radius=18 if style=='Card.TFrame' else 12
            normal=surface(ui.root,fill,p['bg'],p['border'] if style in ('TButton','TCombobox') else fill,radius)
            hover=surface(ui.root,fill,p['bg'],p['accent'],radius)
            focus=surface(ui.root,fill,p['bg'],p['text'],radius)
            disabled=surface(ui.root,p['bg'],p['bg'],p['border'],radius)
            images.extend([normal,hover,focus,disabled])
            s.element_create(element,'image',normal,('disabled',disabled),('focus',focus),('active',hover),border=radius+1,sticky='nsew')
            elements[style]=element
        ui.rounded_cache[key]=(images,elements)
    for style,element in ui.rounded_cache[key][1].items():
        children=[] if style=='Card.TFrame' else [('Button.padding',{'sticky':'nsew','children':[('Button.label',{'sticky':'nsew'})]})]
        if style=='TCombobox':
            children=[('Combobox.downarrow',{'side':'right','sticky':'ns'}),('Combobox.padding',{'sticky':'nsew','children':[('Combobox.textarea',{'sticky':'nsew'})]})]
        options={'sticky':'nsew'}
        if children: options['children']=children
        s.layout(style,[(element,options)])
    s.configure('TButton',padding=(18,12))
    s.configure('Accent.TButton',padding=(20,12),font=('Segoe UI',11,'bold'))
