"""Assemble intro + episode + outro with music and whoosh sfx.  python3 final.py out.mp4"""
import json, subprocess, sys
out = sys.argv[1]
meta = json.load(open('ep_meta.json'))
dur = lambda f: float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f],
                                     capture_output=True, text=True).stdout)
TI = 15 * 60 / 128            # intro length (music grid)
TI_V = dur('intro.mp4')       # actual video length (frame-rounded)
TE = dur('episode.mkv'); TO = dur('outro.mp4')
woosh = [TI_V + t - 0.3 for t in meta['whoosh'] if 0 < t < meta['tout'] - 0.01]  # question wipes
woosh += [TI_V - 0.3, TI_V + TE - 0.3]
ins = ['-i', 'intro.mp4', '-i', 'episode.mkv', '-i', 'outro.mp4', '-i', 'intro_music.wav', '-i', 'outro_music.wav']
for _ in woosh: ins += ['-i', 'whoosh.wav']
fc = ['[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p[v]',
      f'[1:a]aresample=48000,aformat=channel_layouts=stereo,adelay={int(TI_V*1000)}|{int(TI_V*1000)}[voice]',
      # intro music: full level, then duck its tail under the first words
      f"[3:a]aresample=48000,volume='if(lt(t,{TI:.3f}),0.80,0.80*max(0.12,1-(t-{TI:.3f})/0.6))':eval=frame[mi]",
      f'[4:a]aresample=48000,volume=0.80,adelay={int((TI_V+TE)*1000)}|{int((TI_V+TE)*1000)}[mo]']
labels = ['[voice]', '[mi]', '[mo]']
for i, t in enumerate(woosh):
    fc.append(f'[{5+i}:a]aresample=48000,volume=0.35,adelay={int(t*1000)}|{int(t*1000)}[w{i}]'); labels.append(f'[w{i}]')
fc.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,alimiter=limit=0.93:level=false,"
          f"atrim=0:{TI_V+TE+TO:.3f}[a]")
open('fc_final.txt', 'w').write(';\n'.join(fc))
subprocess.run(['ffmpeg', '-v', 'error', '-stats', '-y', *ins, '-filter_complex_script', 'fc_final.txt', '-map', '[v]', '-map', '[a]',
                '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out], check=True)
print('total', TI_V + TE + TO)
