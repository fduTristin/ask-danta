from pathlib import Path

root = Path(SPECPATH).parent
a = Analysis([str(root / 'desktop/backend.py')], pathex=[str(root / 'backend')],
    datas=[(str(root / 'frontend/dist'), 'frontend/dist'),
           (str(root / 'skills/campus-research/SKILL.md'), 'skills/campus-research')],
    hiddenimports=['uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
                   'uvicorn.protocols.http.h11_impl', 'uvicorn.protocols.websockets.auto',
                   'uvicorn.lifespan.on'], excludes=['pytest'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ask-danta-backend', console=True)
coll = COLLECT(exe, a.binaries, a.datas, name='ask-danta-backend')
