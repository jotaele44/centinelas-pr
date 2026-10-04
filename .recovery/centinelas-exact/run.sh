#!/usr/bin/env bash
set -euo pipefail
ROOT="$RUNNER_TEMP/recovered"; ARCHIVE="$RUNNER_TEMP/centinelas_exact.tar.gz"
rm -rf "$ROOT"; mkdir -p "$ROOT"
base64 -d .recovery/centinelas-exact/payload.tar.gz.b64 > "$ARCHIVE"
echo "a1bdd30254501414fc6e38fe83ccc61759b0d20b83a0e7f7e5743e337d3589b0  $ARCHIVE" | sha256sum -c -
tar -xzf "$ARCHIVE" -C "$ROOT"
python - <<'PY'
from pathlib import Path
import hashlib,os
root=Path(os.environ['RUNNER_TEMP'])/'recovered'; exp={}
for line in Path('.recovery/centinelas-exact/member_manifest.txt').read_text().splitlines():
 if line.strip(): sha,size,path=line.split('  ',2);exp[path]=(int(size),sha)
actual=sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
assert set(actual)==set(exp); assert len(actual)==227
for rel in actual:
 d=(root/rel).read_bytes(); size,sha=exp[rel]; assert len(d)==size and hashlib.sha256(d).hexdigest()==sha,rel
print('EXACT_MEMBER_VERIFICATION=PASS');print('RECOVERED_FILE_COUNT=227')
PY
cd "$ROOT"; cp package.json package.original.json
node - <<'NODE'
const fs=require('fs'),p=JSON.parse(fs.readFileSync('package.json')),s=JSON.parse(fs.readFileSync('static/__dev/dependencies.json'));p.devDependencies=p.devDependencies||{};for(const[k,v]of Object.entries(s))if(!(k in(p.dependencies||{}))&&!(k in p.devDependencies))p.devDependencies[k]=v;fs.writeFileSync('package.json',JSON.stringify(p,null,2)+'\n');
NODE
export NPM_CONFIG_LEGACY_PEER_DEPS=true
npm install --no-audit --no-fund --ignore-scripts
npm install --save-dev --no-audit --no-fund --ignore-scripts vitest@3.2.4 jsdom@26.1.0 @testing-library/dom@10.4.1
cp "$GITHUB_WORKSPACE/.recovery/centinelas-exact/recovery.vitest.config.mts" recovery.vitest.config.mts
cp "$GITHUB_WORKSPACE/.recovery/centinelas-exact/recovery.vitest.setup.mjs" recovery.vitest.setup.mjs
sha256sum package.original.json package.json package-lock.json recovery.vitest.config.mts recovery.vitest.setup.mjs > recovery-hashes.txt
node -v > recovery-environment.txt; npm -v >> recovery-environment.txt
find helpers -type f \( -name '*.spec.ts' -o -name '*.spec.tsx' \) -print | sort > recovery-spec-files.txt
count=$(wc -l < recovery-spec-files.txt|tr -d ' ');echo "RECOVERED_SPEC_FILE_COUNT=$count";test "$count" = "5"
:>recovery-spec-classification.tsv
mapfile -t exec_specs < <(while read -r f;do if grep -Eq '(^|[^A-Za-z])(it|test)[[:space:]]*\(' "$f";then printf '%s\tEXECUTABLE\n' "$f">>recovery-spec-classification.tsv;printf '%s\n' "$f";else printf '%s\tEMPTY_SPEC_NONEXECUTABLE\n' "$f">>recovery-spec-classification.tsv;fi;done<recovery-spec-files.txt)
set +e;npx vitest run --config recovery.vitest.config.mts --reporter=verbose "${exec_specs[@]}" 2>&1|tee recovery-vitest.log;status=${PIPESTATUS[0]};set -e;echo "$status">recovery-test-exit.txt;exit 0