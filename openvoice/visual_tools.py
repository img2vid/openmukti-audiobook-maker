"""Create a sequential animated camera move through selected comic panels."""
from .sound_studio import number


def panel_tour(file,rectangles,seconds=3):
    seconds=number(seconds,.15,3600,'panel duration')
    rows=[]
    for i,rect in enumerate(rectangles):
        if len(rect)!=4:
            raise ValueError('Each panel needs four coordinates')
        a,b,c,d=[number(v,0,1,'panel coordinate') for v in rect]
        if not a<c or not b<d:
            raise ValueError('Panel is empty')
        rows.append({'type':'image','file':file,'crop':[a,b,c,d],'box':[0,0,1,1],
                     'start':i*seconds,'end':(i+1)*seconds,'zoom':1.1,'pan':.13,'ease':'smooth',
                     'focus':[.5,.5],'alt':f'Panel {i+1}'})
    return rows
