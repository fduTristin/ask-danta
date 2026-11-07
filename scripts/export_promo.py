"""Export the recorded product demo to H.264 MP4 and a compact README preview."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    args = parser.parse_args()
    bundled = list((ROOT / '.private/video-tools/imageio_ffmpeg/binaries').glob('ffmpeg-*.exe'))
    ffmpeg = args.ffmpeg or (str(bundled[0]) if bundled else None)
    if not ffmpeg:
        parser.error('Install ffmpeg with libx264 support or provide --ffmpeg PATH.')
    manifest = json.loads((ROOT / '.private/promo/recording.json').read_text(encoding='utf-8'))
    media = ROOT / 'docs/media'
    video = media / 'ask-danta-demo.mp4'

    def run(*arguments):
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'warning', '-y', *map(str, arguments)], check=True)

    run('-ss', manifest['trim_start'], '-i', manifest['raw'], '-t', manifest['duration'],
        '-an', '-vf', 'fps=30,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '20',
        '-movflags', '+faststart', '-metadata', 'title=Ask Danta - Product Demo',
        '-metadata', 'comment=Synthetic demonstration data; staged response timings; no personal records.', video)
    chapters = manifest['chapters']
    starts = [0, chapters[1]['seconds'] + 1, chapters[3]['seconds'] + .4, manifest['duration'] - 2.2]
    filters = [f'[0:v]trim=start={start:.3f}:duration=2,setpts=PTS-STARTPTS[v{i}]' for i, start in enumerate(starts)]
    filters.append('[v0][v1][v2][v3]concat=n=4:v=1:a=0,fps=8,scale=800:-1:flags=lanczos,split[a][b]')
    filters.append('[a]palettegen=max_colors=96:stats_mode=diff[p]')
    filters.append('[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle[out]')
    run('-i', video, '-filter_complex', ';'.join(filters), '-map', '[out]', '-loop', '0', media / 'ask-danta-preview.gif')
    # Inspectable contact sheet kept outside the published assets.
    run('-i', video, '-vf', 'fps=1/4,scale=640:-1,tile=3x3', '-frames:v', '1', '-update', '1', ROOT / '.private/promo/contact-sheet.png')
    for artifact in [video, media / 'ask-danta-preview.gif', media / 'ask-danta-poster.png']:
        print(f'{artifact.name}: {artifact.stat().st_size / 1024 / 1024:.2f} MiB')


if __name__ == '__main__':
    main()
