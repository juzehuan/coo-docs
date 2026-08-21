import re, glob

src = open('frontend/src/i18n/messages.ts', encoding='utf-8').read()

def block_of(lang):
    m = re.search(r'const %s: Dict = \{' % lang, src)
    nxt = re.search(r'\nconst ', src[m.end():])
    return src[m.end(): m.end() + nxt.start()] if nxt else src[m.end():]

keys = set(re.findall(r'^\s{2}(\w+):', block_of('zh'), re.M))
print('total zh keys:', len(keys))

used = set()
files = glob.glob('frontend/src/**/*.tsx', recursive=True) + glob.glob('frontend/src/**/*.ts', recursive=True)
for f in files:
    if 'messages.ts' in f or '/i18n/index.tsx' in f:
        continue
    txt = open(f, encoding='utf-8').read()
    used |= set(re.findall(r"t\(\s*['\"](\w+)['\"]\s*\)", txt))
    used |= set(re.findall(r"t\(\s*['\"](\w+)['\"]\s*,", txt))

missing = sorted(used - keys)
print('keys used but MISSING:', missing)
