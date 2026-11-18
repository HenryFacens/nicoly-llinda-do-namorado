import subprocess,sys,numpy as np,json
f=sys.argv[1]; fps=4
# crop label band y=1060..1086 full width, downscale x by 4
W,H=480,26
p=subprocess.run(['ffmpeg','-v','error','-i',f,'-vf',f'fps={fps},crop=1920:26:0:1060,scale={W}:{H}','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True).stdout
a=np.frombuffer(p,np.uint8).reshape(-1,H,W,3).astype(int)
def purple(r): # bluish-purple highlight
    R,G,B=r[...,0],r[...,1],r[...,2]; return ((B-R>40)&(B>120)).mean(axis=(1,2))
L=purple(a[:,:,0:60]); Rr=purple(a[:,:,240:310])
out=[]
for l,r in zip(L,Rr): out.append('L' if l>0.2 and l>r else 'R' if r>0.2 else '-')
print(''.join(out))
