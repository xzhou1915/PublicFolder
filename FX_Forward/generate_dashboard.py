#!/usr/bin/env python3
"""Generate a self-contained FX exposure dashboard from a headerless CSV."""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import json
import re
from datetime import datetime
from pathlib import Path


SAMPLE_PATTERN = re.compile(r"const SAMPLE_CSV = `[\s\S]*?`;")
LOAD_LABEL_PATTERN = re.compile(
    r'\s*<label class="button" for="fileInput">[\s\S]*?</label>'
)
FETCH_BLOCK = """    fetch('synthetic_fx_exposure.csv')
      .then(response => response.ok ? response.text() : Promise.reject(new Error('sample fetch failed')))
      .then(text => setData(text, 'synthetic_fx_exposure.csv'))
      .catch(() => setData(SAMPLE_CSV, 'Embedded synthetic sample'));"""

# The complete dashboard template is embedded so this script is portable.
# It is gzip-compressed and base64-encoded to keep the source compact.
EMBEDDED_TEMPLATE_B64 = """H4sIAAAAAAACA91923bbVpLoe74CDSchGYMUSZEURYry8TXxOXaS5UumM25PDBKgiBZJcABQtlrmWv04z7P6G84v9Ht/wPmI/pJT
Vfu+cSFlu+eWFUsisHft2rXrXgXw7HdBPMuuN6GzyFbL86/O8Jez9NcXEzdcu3gh9IPzrxznbBVmvjNb+EkaZhN3m82bQ1fdWPur
cOJeReH7TZxkrjOL11m4hoHvoyBbTILwKpqFTfrgOdE6yiJ/2Uxn/jKcdBiYLMqW4fmT3zuPP2zidJuEzvMYxsXJ2RG7hYPS7Jr9
5TijJI4z54b+dmC9ZZwAwEW4CkdO4CeXY36n2YzWlyPnzrw778+P1dXVNgsDuH7a8TunM3V97kfrDK4PuiftgXZ946/D5chJLqZ+
vTP0nO6J5xy3PafdGvYa1rBmmiXx+gKgdAbdTrevbi+jdciBdNunAAXBdLsEp9PV4Myu/TXM758G01lXXY4TOJsQtzP3g8FA3Zgu
t3j5JPBP53N1OaE9zufD/lDDAggMJ3BFEwZhdzpVt9bhhc9vwaxwOFS30oUfxO9HThsQ3nxwTtrwg3aC2LP/W90h38PuK/r1nXPj
TOMPzTT6U4QEmcZJECZNuDQWQ6ZxcC3PceUnFxFsvC2WXUVrxjYj57gLK+rXF2F0sYCz6rTbV4uxzgkj58pP6nT0kqZTf3Z5kcTb
dTDiVxwn8QNkxAv8Dexan0XJbBk6fuYMu984vW88tsH+sed0uvij06FdHjc8J4OjSDd+AvOc7mkSrhreAXDb3ziDroA77AHIdh9+
9PvEAScW3OOuCfdO+xRQ6IktzUHKgGFX0fJ65DwFiUs8Zxs1UwDQTMMkmntOep1m4aq5jTyn6W82y7DJrnjOA+DFy+f+7CV9fgKg
PMd9GV7EofP6qQszJRRjOSBs5MPv9XYF92YjJ/On26Wf4IXUOHs82NFoGs5jEGZxwIz1YjjiefQhDAToaA1qRTv2TRzhdprhFZAh
HTnreB2qEybdMnJcV1yKN/4syoAIcDb5825GKx+FBoUPEJWnwsQQSC/+tdrdhtPZfDAPAS7AsdiTT9tBeMHP0YTRGZYAKcAM5AIQ
6/VAlPCH5G4/vSzDOouBslkWwxFOlwDJXOdk8I0pgdMtjF3DcYbLcJah8t1sQW/SYY7g0wJOMZPC2EoX4XJZcFpJuCS9IDDkMgli
WO/0em3cLmjzWR1k8Run6eCVRmNsS7Xjb7NYnrEfBKQUjlGTtJ2+JABHBm1PmEhkgijdLH045PkylJTyl9HFuhkBB6fsBuheP8nE
7T9u0yyaXzclzwCdwBBNw+x9GK7FqAt/M3K6Bv0R4SajM9waWJi1pkDyAKho4sQAdXC0idgsRG4em9ObsMplfncXSRRYVO4NFGpC
6enXYCJsylxL8Bop3BHyn5PGyyjgmgdtTwd+dE5BB7WOlenhGhq5bQvQOhpVDNWKBqpItxbCbw81+B+kJSGph5MHi9IXxsSe2W8Y
6ocJTOdYYUWX33OqDNtShSzDDDUIHjhxWbPVPg5X5jGG1+E0id/nzQ+y4yEb13HqlOB00i/FqdXpCZQcJws/ZE2SZdCYwHXbzSZM
Zn4amkLRKTeWGjazpb/a1JGs4KZcvYcfp5oGMvAb9Kto1usrDFEVKatrkpIJa5O8wcMl1mRWJj6alSeBfp/gZfxZKtU0LlwHJkqB
n4XN2SLaAB+l8TaZsU8SvbxssBPGbZbJw+npqSZ3QoPBNYMnDYYhT7NcVNBoOOoH2KBilu/aOkhuz2HuJqijvPOTP2o5P4vj5dTf
o18PU6B7z3RYqlv1W5KeuFlD9XzKUXU0DZmjeqeHfjfSHEg+GBrHEyTxpjmPlhmuCI51UkdQplkV1GsuwzlYVfkxQULnDUOhNVDs
rsxv5mfb9PME6PQgPqxkLYZGM9AiLG6KTvKW6MQ+JnkC/fY3RQdQZEA0q9AW6rfalAhckTOTWPksAq3j4WeyT7uEjiVBBQR73U7Q
bRvYMa9L4ajHM50e0l0xfds57pEjROehfAVy4PIsEa1JHeucUbT1fdzyBamk7aRUGZYT76R73JUB7WybpDiJxwHSRKJ15B6ptJRg
RfupE4Kh9AR2tKRxXS6lrloeHZF5tIiv0OV0NDtMf4L3G/5ab5Ibb6xS7PAc93GYsb9p1++GeKz6qaZXqLYFQ/TZubOACNz0N5ia
mbigikL3LYxT7rg/hQMCeR7LuThVmmb8oGKicXE4Jbd+uYnSaj8U/24CC22WZHNg6dU6xaBgE/pZHTYMbL3yP2AmoDNPlOPPNFy3
XPnnNM/MT4LPMtCdk2Ktz2ZSeqZQ67D77NM+azDMWQMgIRdueQbHpnR30EfADAbD0EE+my9x5UUUBGBKi4ItwS0AfjTy5xmxZhEX
JGzRJllTR5C3eUzGhbPIaVvnEfZJj6WLtHcBCS8AaU/X4ehk6ORBtdbQ+A8ETt9Ic+lPw6XtrHDjlHOoLVca3Pu8E90+BRe1wn3W
F7/yl9sQj4oxYhZvOMtUO8992lLelypzmG1XWUdhHWc5DDrsMDSCUB6yiCDKRicgjBfXTRTOzxHf4y8ovgIpZNMc50sqSNQxaDjQ
WdrjiGq45qL3wqUxY30bP+3U4hGmrE2OGLbz65APJUXQkEAmqobMHdO1nMz5M8SFLI/pJyEWPPm9ij7UI7AoYI48cxqw6jdGlqgh
0RS6BMi6XWe2UFbwoLlJiPqSaJbq9CT+K+M84DL8ZyRMOEwGSioJ6ywHB8lJ+1DFMTxMcXCchO7QlurmddSgW6wXuqQXhKCsAG0u
uQfSTMloazgAKdWFtoUXDBngmGPBJmNWD4MUf7oM2SfTFW1rhqprBCSsnnGAnGq5twNltV8kqzrybG2q/khOIFwPF0NejtlObSh9
8rTbhypdU523lEFbhhdheSbw+HB2NeEBwdY6UN3Zr1BSgzykqET7HB+ifcANR33xEHegRSQQ5xJjFfAuZVKPNc+HGTjNs6XpLE1k
E+3TdXxOO3eLFpR5krzA5oayAyj0UfhYUBmzS8MfU35blY5nKaTiRJCqIvQwgsg7iRqeMDlNPfb3OsxKPENRWaHUO2N5Cx9ZA9Cj
K2IZpwWh0mw7Bd03Df8UhUm91fVaQw9+dhp5XLDWV7mpzrE5i2FtcCRxy62tYPcQK9gvtYJUiC7yy7r9HCczhcNJyK4URicHir2t
WPpafo60NeY9ASvFCVRCASw/yGm9k7YSCaRIk+KMpu74EDAt1GyTcy/j2KW/SdHx5X9BzLAA/UL2K8RwkbKvAtTCYDUQ2dnl9dj5
E8T2QfiBvF2ii25UOm2R0DuEdLJKzN3MWxDYjLl7nXm3a1D9NO8aFPnxrY70DEjbjhzM8x3gKwBx51GSZpiYXQbAb4H+WbnFlDc0
fVOYuvSNmeqjNpGHeubM1nq7win4G7MXGuI0Xo4MDM+8a59KnuSyVwFbFbBTodU+UcS/MzsJ2rOg1EXMqLqfJTKvskfrYe5b+i6z
60NS2sNCz67LnC2ea9mjyad+cBHeztzmUxOl+oegN0CX5NRPsWGQx4PZwJOcB8HAWXZ6z9rD3NLVItEtpGnvMG9ZdJfYRBfXFd1F
s4k9Ulxv6B74Ig4OiU90ZwqIC1By01jmWerZeRxnXPd/ij/S1ZQv12q5vO7hbmChPTDR3JjOMFoCrtVBFrTdh0kSJ/beE873NOR/
rcIg8p26BqLT7mPpXuYTeHJwTwqhyxIHYmkrvikPAsWEcnxOBiY6vD/B6D9gLQdYvwc0qBmhYRltXVmKvgJPq4CZMg5uYpjNFmMW
0wRREs6YqWOoa7vUip4GuOICJY+O5Ow9JSS7+KkmWqmfzyJwv32b89ZAOhVFr8OC/xI4rGYicGDTYJZz5DQ7Y9OBkRBEkSRPedV6
YRNPJS2MQhwfpmmFajbgpD36znny+5+Y0Q3RGqxAV2Qgz7ilTRKmgIeP853vjvQGRqt1ccmsNetaxKJI7/h4LNsV7wyGJyfD07Hs
U7xz4g9PTvtj2aB4Zz6fj+0+RHGRug/vBPNwEIZj0WR4p3s89E+GY9VdeKfbGxyH07FoK7wznPaHs5Mx7ye8Ewx70z7dlo2E4GoN
B4NgrHcQauO4s94mk4YOB7f9x17v1Bt2PGrz4PRk/YBca+lmXzN4d+a9+cl8OjY64O4nkb/0fgiXVyG4pL6nNbBpoEVHmqd34Xiy
FcRsFfBsIb2DB5k94D1VJCyenWUpsCei3pITe6mkxcjpMp5dqsDE0Hak7E5RXj2916o/oF4raXC6Q8pt9LQQWHRSGXpONk1YwTRL
h++KG50M/LAXRTNh3aHtSRSl3dqmkeu0ugqcKnJY62nmVfOITGdOiLz7DOQ7zZxH4RICeUT/F/+F87e/Oq9fPgKDsVyCEKaubntZ
nkZHvFeM+K6g16Xk6FR3hnK4Zew9ahdvQWNxzV3Lo7qzOjhyak87W1WT6g/zmRNWMBII5sM07psy5WhIIKoUuz5WyOfCOqCWPdVz
k6wo7mnamyN6PNAwYHS6Mw1mp8HAxivHDAWqAhHVCGhkhsqKvmwjJganx35/OrSAD+an8yCfEBeGGbbcKaX6Ti95mosVhcPiKLrF
R6FyImYps/qQ9IKNCOlVGktmHWSNUjDKsKymozp+FUA7G6Uno5hq61l7shI+UrTd0hpShQ6zaz4aM5wUaqyqGo6eRC3I7rGiqToL
g9gl1ZbCmNSqg+wfma9OdCt3V1SBMFWYWS7QlFiOLXYFxQIeomhZICpWiQq1nm4oSfAUlgG0wxvmagVaor+CYEZiTUuk9U/1PFrb
zHdpGjKvxZU2FDLZOTnu9DuG4tETNnoahpoH2yWKTKeTUEThMAzm3VyKZZ0tWLKojm0eDTPZcgf8pdP57JC8zB2A3pvPc9mRvVYs
p3vLbBgliKxEgiEotKSmSQR/8rwMZ9MSgeSagOXJTspE1NY1Iq2SVzV78nJFPp4WYIkAljtzN5orp8WtzK1rjPWoFdXrjrtuNznH
jYLJnbSyxgAewO4sG3wjUKXsBkMEkdgVR2A3OGzU2eX3JGLGSvjF0R9SqWw9Pd5DA8FWPjviT32Jp79MK3tTvI5MTMgqKXU27LTZ
5LXfSMEecOVEP3LjnEX3RioGUwflx/KAQGgjMZF39yGTFmgn00VBoBQkRKmiK4XV5FOcqBHohZqU11mBh7+2f2gmsggkuhWmEUXZ
KcYKDemNJZRlSyNwCYnboUG7rYMCbznObgqFXMm4JuI5eRbAyAbeWBZP3KR63U3eyxGBCBLAtmzmSuh7W4qyM+8D/ABDDbYAi2Bu
8r6PqI90xyjc7TEncntMlQBUSlwirUWG4anvn4yVXhL7AXduWbAOqQ5Fr2GOXnhTK/XxSl9X9EoiOuojLLbmO7vRsGLiRXUM6/Gk
znEfH4zCCH0wH4rfWAD27oSnSDHjb4xdd1/l9OXNQUIOIr3bfZVXEAvEcnOX/77RgkdyWXUl29HoQ5+LXBEgwoK0Vfy+RWpfSPQp
6yKgtgUx6B8nj4MieVx8ojzqe8rizF86CpRXfKtMukzaaHBu8mqubLgGW/kIeZWxOESQO58uyIW4sfU4dI10dJ3J/n+I1C8Ol/qT
Iqkv2x+B5MwvAGCVW3RwtgYn5pbX/j9QFxhhh+l7mbd0P0wyPxsxA0+rUDGANY2TawZB1wukBiye2anx6ISVy7RMthwg1UOlf7R4
6IBwyMKm2h8xRgoFOBI9T4c4HwICprFSy7GDfSDSqj5B5YmyFJQNjFprpNuFXpcy6SWRoMnJg2L/qSDYMdWJhggifCOPmzoqtDhw
QJ63Gs16JyxWtG7uZUZ7QqIsHNOxWWCrVlNFhfPj+bDYVN0JTsJ2eLp/EaMXARbUoLVzs1us+2t2zXdldC5QrrdQvYPvu75gu75R
LYadXp9oyu+ut6sp6EvTvvVM+1ZsATiAMhvAVyM7L45TGVJCnY672j50y+yDvvoX1/mg8QfTrqnz+YIVWl9T2r2c1u/oavxkWOhp
GUquOM4cWyUw5oDtLC1RqAFYnHorZdwe57OlepCVblcwoFCKD1OkOUiFEl42ar+ol868KQiCSlfRZLXI6RKkB3czWrI8oQpmuyKY
3R9s2mKGiseqfLTa2LtsJWxk44d+tkfsfTFnmF5ib4fxozU+T5GmE5cSIC57fcsZy2uc83LrWRBdiWFUcnLP5UsvcveoZOeeP/n9
2RHcMgeqT/B5I6bx4p57/nOcZHPgiNjBB6KWwOyg4MKzo40xb9HBF9GosX//81/Ua2mm185Lfmaw3Y62vI6N+UHbgVY70vdI/aaC
TqoA6TpRIC48xM/nL6/X2QILnE7qQzgEuOPUEkiyCOWe30+deP7teppuxvgeHWqERdhLKpY9gp/uOewTjxLvnZtwte2wM8ajYx9T
phPEkjyz4zr4nhDGlhP3kZ8upjHWOXjRJ3WLaKNXRkuJQ4+muudnkXkFk/Rw9Sg6Z8OJbnTnFfCte/4s9lE0nFCcI9DG//uf/y/f
Z+l2izGkvJWOIsvTCy6lspLrgJywp/ee4tN8rsFj+OQfvi/pQfxh4lIM2YP/XXyUCgiGaTKX+pUvw4mrt2GLq0yJT9xOa8hpzSwZ
4Jhs4SzPNj6E9UCE552u0xn80lvBIs9OWn1n2Orjtd6yBx/g3/O+0+ld9fyu0+XP3sJfi05bv9DsXjV77hGS6epC3weS1Xn48hdN
CogUGmnYG0fwPBQpHO3JRgfLPJts4rZm6ZWHWuYI/tCJy+uDFnURolaOFzD57fMXeEsKCbuq8xTrMuEwOVsyoNPtE6qUmTzMrqH4
T7cpGJI0dbbryDrVeEOyQNHsxL3/7BkI3nJpzkjPjtgwXXUwdArFjQtYibxhC4KJqNJb3KQoWQNTHOGLiMSuUSIBAPIU6O+Jy57u
M/rkShSxfJDPPf8RyIyldQqEC1SyPoUIw6i8DjOq0HO1UzkN2ylA9W1XoMMcaTGX4RXInBDo1NK/fK+fuHdsfDlg799T3/sn7J4a
5m+5//vc7VM6jBdI4vkceP3LEoD1Ah1AgkfCK4QY5hf/xeEkCNTEX8BgHEyGp+vZchtAICnaOzd+lOSW/tz9H8j8D/0kub7dvmc4
5VY7vv/4EfavvLxPbSw//J9HVTvdpzCMxCr3L/il7+mKrkt0r0eMQitbvQSR1nDvC829HnhYlD4/W3TPH1Ls41ylAha4Hl0wbOe8
wYdVvCHG3Kas3y6JUqF80aWroK0RuLiay/A+DC8fSljueeefkOTMMSI/QY5cgclYGEOfW0MP8gcLoxqdGiweKBtNd00blJEPfpYl
8G9xrnxV+AAXBCSIwIF7mWPBWqUqRxCHF9wH+vy/v1TMZ/dLZz/fM/u5MfsI93SUiXdSqh1TNVvn5JeMPC/i93i6R5mIR8RhENn2
++oFMZYgyezaYbG5w+7uBVJ5rkbm5TbHKbH573A6fJe3PpV9+ka2slR7OlqbZoliVw0s5hlYgSWGiF1zDhV6XXk8wh0AfWXO25jT
RImYeVHSrmNSY+lHgQN7ZI/WiVt2qHpkx7zabtgToKZCf0gFan6HaTMMpbgJ5A0mg/5JZzBn0RR5OLryyw037CVOga0UqcActkZg
L54p5S64nxCmbg6EJKB6aM89f+CnUcpo7mxTcA2AC52UdWI//PFXagJ98OKZkwDnteDKD/zKE6ANDNxu8K21GB0CYVK6h9cBtkOd
WgDFvwAeazkP/ATGrC+yRYoLyecsmdFJW9rxaGa5iim1ksY/iimlERea6mCupLMgDF9KRuXGVyQjgVzUsisbCVf+ZgOkrGbUCk5Q
3VmWHtSVg6EbjWt4tUxVPvxV/v1Aj8gKtZvm1Bfc1XTm+XN6OEkpQRPHowIkNZ0oBLtEKebUYi7PVO38YTM6nA5HXbSmKz25wZ04
IDzoUCCfz0jd8LQmPsggrB3KDmY0nBV7LzOKS7xeXo9BTmA8aKw0mkcz9owDDJvF7FWxM5CSAFPDK/QjYCV8DW0UBihMKLV8/Yhy
xhQNLK9J9JIQpRIG6kK1OacEgsMfv3sYTzF1hY7Xg9f4E84Yf5HR+g2O8LdnMegJGaPgPXC9JcSzI0YgylUeoR0hwp2lsyTa8HB8
BkyegfP9/Odnj397+PIXZ+K867a7g2b7tNnpet8v4ymEPs+Rct7j1y+8zrBN/3mn9OursrH/++dfPbjIB58MKgfff/2Iw2t7/U71
0MePvAEf2u1WDoWIwmse99lYhnfpWAg7vK4Y2qscCirXGwgqdAb9PYN/8Jr9EzH6uLtv9BGC73T4hNKRoO+9nqRDpxoJMAVACEHg
zslwz+hnRzjjpACHx8+dVwmlGr3nv//Ra3Z7cmc5FLSx/3xfYxy+uZKhT3+EoW3BC1VAkRPk8oOKgcgHXYlnxUBkgmanr/F3yUA8
o2MpCMPKkT9wfsLt7BlJZ9/vVtMdT/5Y8Een160AqZ/iyUnlQHbkck9qXD+vAtSht63z6RfpgD4fPexWDv7+wc/8dGDs4LRyLOoL
gWpvWD0UuETQoNurHEr6Qu6tGgNkFYFsp5oKeKgngghcCioGg74YSG7t7QPN9cXxvnNDrum3DTq0KwaDvugpSvT3jGbMMyjAIacv
pBLIH5ulL7qSx7vHFUNJXwh6DToVI5ETzGMoGUj6osQW9HP6Qp5Vu2IkHlKvW6YA+zmNIcg06FePpNMftKspTxqjb2jKdunQJ0r7
nlaPZKfeE4Dfjb/SHIqHPz376cVLcCZuHC2FOnJc/vil6zEHCa+wBzDhCqUbaQw9tOk6u7EG8qcXjx6/AIhvahrEmufUCBD+QfNr
b/VJD++/ePErTFqH752XYVZ/UwM2wLFwyPgLjrD2tqHPeHD/5dOXv7386fWLh4+NiUBqWu3FM2vGy9c///zTi1e/PXv8vTXhBzbh
iTXh5/tPGW2431fjJ1kb6Y8Z8/kYtI0cCQ2HvXV24lsTavwcrKmIpJrKPjFExHO9/LSWEJgn/nv0z5G0nHZ4lZflXlJ1Fu7V7Nps
jYOYb9fM+4TFowxcyGcQe9SpG0H7BhPcdxKm22WmrcNWYplOWKGmX/3XbYyh6cSZ+8s0VC/2TZw63qYmFLjbHvM/z+jByxaLX8XF
uxOno7AQeGAoDlNx/BsaJ9FxnGju1Nn9CWDk1vTZ7C5H7NtvNQDOXafzVpvC93SXPuvIqGew8b8QdqY2+jv2l8JlxwaYKHk1XJqP
NbFj9G1ttumiTgi0siRa1fHx2TyNJXiJKq4h7gosy0HKAdk2WfNxxusSJV9s8Gt1gC/qWP20eYIeEU4NnuDMwlgS57QgWMIvAagf
/csftk8eP3lyBNxca7SI4epHf0ju/WF91GhBbE5s50zOGS9wVFvs0cD6gzhehv6aDaSRHjuZBs6wmWQehcsAMciztcktbCBnPOd3
cEZ95AC2MUa5d/ga/q9vJKvsRpjyAh0G597nT9yn7+CYODXX2+VS5xSG0RvM53vOdOs5s9n1C/+9x0J4+gvCUfj9FuWF8BnbPA9B
7oTPa2Xxa+xveeinYb1hj2SJponzI3Wx1cUSuXGw4i+cq9jijD9rzsePztG/4Ba+PopamE6ps/sN5x7tzBkJ2Py6Sc/fwSkHN71d
E352+c+vjxggpEADF/jddEu/cFv4mwFsRekT/P6lkGFNI+sSTzwaWh/lx54gRjUapkztOcZoDVIRBQ47GkpDepgfYC2A9pEq0VNf
psNu3zjG4fKTpWMdKUrvpHjmmFp+1wxSkDKBjCEbTrZAtNEsPca91NmO3rTfInVqP8aO3IEv0iDbddCq2SJ+Q3c9IbG7YmFXHTd1
HK6IyaG8abVawkQSmiiMiCCIILZu0wk33rbSOMnqjZaf1ZudRvFS0220DH4Wmbo6w06QkTU02NqGYcetHS3PyWhhQKxMfwCv1AU0
xuD3nz0jHsexwIV4TS7XMHXYMo4vtxvuFDxH9STX1/f95t3XNwza7iP7C1hg987DJd7mVG0xjBtDhjSXpLXwiTYIE3i7kB1xCnlK
xYNvHDg0en2E9DD4GE9mRkfC/fIc9jojuPCC57hqnqhmj5g1V4zM1tZ9rs9CQbiCJDa4R4XNO0VZruJY49m7fciRt/aGz31rageu
mMHRuk/u1gNUwOYEfFUlOylSweecKVoXIADGudOZNzRlqBQyofcLc1pgqXst2B+oM6nNcGXz4j1gt2zR8qdpHWfQvSaNwz8bzsji
AKeC0NZ++HWD7qZHTtRXWGtnANssos4f42hdr1Gy9O//9u9OrbHDvz/qR4N9X/rJFGjQgzjExPQ2rFqmc221xIrX0Z/Cuqwi5LTg
T9M/4jcnzJN49XgNbkqY1im8IT6RxYYCr4R6l4ENJGiBE97ACfhbvfcAlZP4oHGW0MXilmcx9Za+PQuX4lbE026vQ3kzCYMtuGX1
FN/Ph5fIk4JPYB0JEW7F2g0dANX8DgEhWVjBatjAiNeM/XIloJyN/QuxBVBG7t1D+PBPMdpbxQAlJ44dw372PF6H18xJ9kR5jkcv
6vxRoXBfnEmq1HC1v//5LzXTfMj620SRgiZbZob67mCQHH8OkUZ4ChR4A7/AV56uIfAbWfcH7P4A7q8Kbh+z28dw+5Juv+mg1215
6UF0Ya19xNBB/wLhtNsAp+3Ib1SSe1vRWyImTr1gZgM81Cf4DXp1Bt/wbhj5zuCMBOnegdL4+usbBnL39Q0D03m7e2eZTtC3/GBA
aTI45w4iWLtbAxRrtV0VmOJjJ1eH+aWmr0FhT8CNP42C5XHg7lW7PaL///mdbdxx7NN1tmzhhFfRKnxCi9Rr4br5/QPQTugooh7r
Nok0qMOwVQeupAvQYPD5OkSRqPGvMIQLGYD55xi/mrP2+tXDGikyBpWhWMLVEP2DKqzb22LukeHnsfyBxZSs5zMMHryG0UE822KF
DK3e42WIfz64fhrUa8JzgmiOzsOEocqwk5y3xxYVDp9azUaD9cpgHFegl82x+MbeCcszmepCqlClMjhcqULfgleboeIwQbL+hk8H
yl+DjGDFdyCUkVKdCBATw+aH7EkVVEIWp473wVI9+TlYRl5oLyDRB1uCEtOZRDk08PsRU52llRBp2H5oZpNmJUR+NC3NfyBPau8a
oiHyIOjkQh8G12hcyAEHVaNcBGbDd9S8gB2lUqr+9lcIZ3VBlfENqEQ/19qNOlKN3r3bz5N67yXgGK3XYfLDq+fPpEQc4u9I2dUE
I+fLvCvsP5FdnaoNlr12afT1DUtRK5A7t6zVyHgbk3teeAufCDef21CvV2KNQ0Bpfm3HmhyMJz/Mtye5MJp8Evq0U0dW3HpUgi5/
B6RrtWfQ2tp4/WVMrFVLa/cuGMgMJ0cQdeYZs6Hi3YhkSsXLE2s73IvO62IaF3lBjKN8x081ooqelttXwzhiEy+j2TWhAh9ru+rd
VEH78eg+gsltAaW0DPlcQ5DoY3mnRRMs6qkp1c5YfuV/+J5bDfL68AUvENoUy0uJxQAXtrNfhYg+tH+QZGoW8J/oNRwT7mgzo3gk
d9pwvkNH0Z4JPCLnmaEA3GlUzZc6werBw6fkPksTiFdgYHMhe5LMkGrxdBnJaDXXk7NB+jc3ip3gjlHuEIGnB3Z15SO/tEDulj0U
+/WNOo3dN/yBMmMWYJWbI85BzijqdjuAsQWhXvjrS2Szqhi4Tm/q0NLzb7QLb+08W0qxOxYRQFCkruRJxDoEoFPmZGkIvPFllPzW
aZq3ptqtjx8dvzXdtpbYaRWyjviwPoVLDXaPZxtyA/j1xn4x1JvkLFFkGyOKiAD/3ZnehHeWBaYdoTd9aUzOXjYmedxID7zdSTuj
MzHjtywwVpFmdXaNk8J05m9CxJIH53y3u9KJ023RPCBj+RR83T/Hj2XsPsHQ8AyEMDWHrMSeu4F1+J88NMzR6paGomRploIqog27
09jlEUPFYSKng6c2zXe6GBaFd9pqLKdg56heZtgFyW+qEtybb8/Oa+7bowuPCob+jBLj5079xql9WwNkvvVXmzHWm8/o0zKjD+f0
4YI+uDUXP9w5PqVbLt3CguYYg9M3EuzbsgxbiLGMT/VEj6dxFfoZRHu2sZKxuFmL1CyGrIGzoZhJ1GtoVjE8NaKfw0NjMVL41a95
5saoirA5+yoTDbtyAqIk6ybjXDGT1S8OCcTVXDbLUEi1Wz4EWoOo1tgsYY1lE9RkJixDAlAxWELBdAUHnOPvPXGIeFYaFCwJ3rMo
xbryKr4KQQNjSev2gHIhlzg6EXBROW0Z+0EYQDzGGIsXFHm5+J7zjnkBRXd3TnoZYcj2jgn5O93DYckZaXWdmZ/NFg6r7ulFitvS
xA+CL0QQAgJaLE39i9BsLOASXQpVPksNQAGhx/jNrohdCJwIITU9mgSqg77xVXdOJbejHNLdVuYnAB2lKcTUolEnxYsii2h1H7B3
irPkHUhG+IIu1LV8HX5uxWs8XvRQmYfBNRO/y7oiPEKohQ5Mfjp7RbqY/1/h2Gqv8PESHuYzWkIUugyobX0aEuotmaneWTvCX/cJ
cJ2oyzW48AVLEdKedS8+cwjnLuHITTodxED53hdxTKrt3Svob9Jwrw6jVA6zgleZxAo6zPEVpnAMYs3f5h9+E34gvimg1pBfH7EI
18BP6Qb4klpbxN+t+BLUh/yEh1jHwt7P4FBHcCEJ0b+uq8J/je2Lre3MfSBRUGs0zJUQjM7JzMZWISrnkwaqm4JgUPjxahoGoAud
NEdqojH4nvzJBPmIQl0Y/XoDzxxLNFM/BWlEYk4YTXHqewgMwAayCxNzkqNNEQKMgFQqa1J2tuptCUZ+GmejDZ6UmnocIQORSUnu
mlLXucw1ocai6kl5zhpHQfxLqdCJyBO08OmT6zoVvlUsJakhM8433MWTUXVhNrsBoRxoQzjW+puOjLn4wr/4iVy2LDn68WPby2U2
8WJHg4VPNpbT33h4m8+SfuDKvwx/jIOwnvkXHqnCHzFIJNdOaAhcImQQ1Soz0FJZyBfC2VqBqS4BNfi8lrwykX9p4/HFHPGcGtXA
N0OMwW125WRNuU7wb6vgw4cJR9fYH+CuFRUbqobILsBqVEHkkFyIP9yxtm1WyJpYpcMj3t+rj2RVtgmbcD6BEffao7r6eK8z6tqV
KhYeUPiOSaSHeA7Hg8ZdNssu4N11V27hHvEMKQlVp0S2J57O81h6zjhHTOlO5KG7PKfmemaulz9pqVIEcBMFA+T/Ib1AXEFYdGGy
69GCjUMmbHAx4/XHrsRYAUBc8dXGGq5BdAVT5UuPFXZMTCFmfOyD8iwQ1a+0Sjf3lBlpkNkounXvFYrvKH/1SjV4MnjgoBYjiZmy
hjkW817FgykjZo1Gb0cbjUkFMZxS5dbwINapFcFQzJsbnkzWoqRGS71Ujl4ZNLGzd2oOLmQcJABpVN429AM6MYSPPAwLaTqNhzzp
Lt/z6urtQ3X7rBpq0t2J67h3mViete+5Iq3hjlyR1LDJxJ5zzp1/vgGB8h0jS4EoWHhixtYN57TgvnaSlON0PbUPj7DSiYPhqDEb
wFk7oZxlMTuxr54FyuT26WqvogYqXYnBbuOuoRLvuc5aDXMbRoepqTz1xhf2/ldwXe5nsPB0m5GSEY+XA3pYWEAv2L8C54leZqBB
3mE39Y3ZmsJeeGUytny9tWv0euGVW3N4MYvdGGUURIO9Tsu2BMJ/+K7fHhtTNFzYTPp51/3GLR2HbzWbMMDnk/a9fnvUb7O3eDXs
eTlCFSxIgI6Yn/Ed2KP9a7ttc5HcueoMiZMbhc1kFufSVG3kkmItbUASq/7lXbkJwXm2BcVBuk1ET0glWyYu3w9dtmWRmUyXfQuU
/voazxVvrJLvW/jbX50/hUncxGpHEgaoWxmfNPYvgBxvgkfQSZRe0lPJ8hln/ZFmGAQ8x8FTfHiIe50LnVwWOrme5s0bbn69wQgO
ImAmXs7bDWvg+KtdA38eFmGI3RINbhlqFMz9cjHH3oiiIB75nABDPB7/3N9MRAszv601INq+i7hl+G6X4fVE3JAZ9LvuR/euvMpr
CLoXhYnviYYFdc0CKN1fpzGTCWjLcB6tw0BTf3RLFuhGufU90Spq4+Cx9563PWwvzE1DVUus795DGwLDFn4KimpEzX47O23MME8Z
5h61HtqP2ahSxV1FJfqsbVTeAKSk+WLKVNQZtNno69FlhtsEPYKdkdDQTjgK08n9JPGvyZ+v63izd3/IJ37UhPzB09Zu+JEUUItj
Kw5NYDaZsCZJsQnamY4kEYKegEgnXzSs1TZjQGQbsaFpXag7PRoWj2ekkze3DITf3goRQR+YuGscmgbQaHdYMK9PljsrmCojuPX/
1PAbrdz/+PgbnFEwE6zczkIHeu8RD789erG6cZoYMq6Fvy6+cQG9dRp6z6Vf4HXTq51dMyimENKcbMaOKsZZy5hxkY8Z8dgZYiJ2
XOtBY3msSHsb0wq5wFDo4qK7xXEhBU0G7kRBvH94jGZzWQ4cDzDVF4kURkb7I0kMhATwXHzHQrhxPi4sDPjkNmH3lbGeivTMU98X
4rHgrjCsMwO6XDhnBRcyBuMMstCCr4qIi/FJZRx/c1hcVRFKHR49qfiEdndYtFQQICk4e0Ii+fhvcTgkHvqN3xfqlNlt8nnr/Ym8
XDS1zqXuioYclqy7XQKOvnOJlBOz78hSdA3QJGZHtfTLF8zSEXBjZ1xjSx9WLenZiQKpxVHTNHJ+KTlxrMugwuPQ/DjZJdRgfQZy
lu9NmUD4V/l9S/HwufcEpo37MYxo06pJUzlpKidx9KZXTf+KPc1Q5IiWkk7vWPJyKys3byQ8rlLCMse1sdNpa3MioVGQIyjJAty6
JnJo2mBWkjKgNwIKjx/4md4p1sRXjQX6i8WEIQHb4a+xqwFfKIhDnSOHHj3BpMP+3MKsMK9g43DLJAOjGntzv6Lbv27D5PolRb9x
Unetr17CLw/KEmES2VydjLd5H+kfsIHsD+45oy0gX3IfNyHuugrxxF9fTm7096S0PfZ2lI7H3onS3eWirwIBFGrZam9sJlZT48eP
Oelq5oRUD8DwrX3l/Gi85A+/zyi4LuDH/YFj3smE8/FcrlllYiVk1jwL1D1qctRcRtYE6RnqC79DCa5yiwjR+M9JvAmT7LouuiRd
r7BJsjHWl7b0CX2tqm0l9fFK3K1BYgvYUOkZPZR5gGIstimC06Q0VKmz55U0QjJLULmC6ymXVPYvNvi5Fqc+97VIWG/ZNDpOJhpj
sPTdXVdjFtQAsGUtbzZhXWf33PwDKu7ISnb9d8w+ivcI3y7vaMz6chlH3vj4aG+zQ7iEQBMOGW8buaSStkaJP3KR0Fz5U/74kbU2
ovOhnjxqmFkSHYTok9w11Itf5EDqmxQj8cOZtj/h1Nj5jSiN8xMhvn768ifeIgsTl9EsxK/hbTdsX1i+Q50Ix7rRmK80W8QwK50Y
pDsA5wkDspN+EAfE+Q9I1WZ5SX79jXm/2Xm7s893Ip9R1Qhy11UPqrraUeNb5F8RCrlpyFn41CqmC9Uw1LavXz2kgdrVC3W10TzR
M1L4ROsT/IIotQD+aMFwfSX4+AT2+WvoA8d75o3nCAPgdrxOwwb9zEc2vi4ArlbOw8/d40vc7Xht4DV9N9Z6NrE+azmPJeqitUUJ
trKnb7DRsE6NxNjiSGRvdSg5WpVN0TaWywima38DLiF/XY+WNqOeKTNrpr+G4jOapvbWK25Xsbh1zeKgYkVJueI/qUpRWpzYGfWT
krLEF6xHGIVTDan/kPqCen8ID8RHRSUxTzkkIw3FnR24MRP5kvP/RAqCplWZx4oSlx8mZJSNIRHLD5JiaYtdEM3nIaIW8gTjJoni
RNoOPU/28SPdy32SXMlYhqY06abaIza1T8Tb2g7NnijivMJ0xcQkVCv/FKE0NDTcIBdPBhKG+o0SKExTERiTojoc406r9KFGemUU
vQtMyasUU8EYI5dWc1lmZoSM7r0PRtrxaJSgZwLVRu29yTEN7/1VGQjMUOwDgU68t6rEQiNUjjQaHqtKPPYDocehpPRpnqLFE1pc
IGuQXzJdZZf3qkLhPSGrMhcGCmQq9NBOcvVTVPmHMbVGBmlPJFsTnEO5ugiS3viS42zXVTxt5Mz41+2iVmXlolEuQWYyvBaByu0L
3aNdsNSPuCNe/WNKgEzOfQrEAnHQcFS0FSD1KxZMeUuguSpG8xOBmuKysyJuznegkN33GL+/xxLLCv9aXblM/9FXiaSTm90YB+Y5
Gfnghg16A3+/LawEy1f1lQVdbCpnvvZIypC4ZTeT72zrxeJto95aWWg9oMJ6eGmVQ1YVtL//27+7I/eu27h7+zqrHQGGyyU3yOhi
kbwYdjELykrjmJNpjLNAK4FTDkj7FmpGCPa6yVIwWHlrjNkgHZbxfdWuGGAkZ3KngugYmSOatK8gpwqB1TiyulQeRdbLOZblvDIo
kajr5UFQ1W9/0a+8rKfJyBer7I3LCnEWlVnhbWe6rFmucJBVZ2r1r6iCJUoytey9mHtztFk5v1FeXXjhrFKfGYxnfnG7m0/wVgqE
kY/VudWwvkDaiqysHi7uX1EfmV9R3DW3LOMOY7LOl8Y30Ls2vvo0ji+xqVrhXmG+esRfHIPMbINEVUS33wceGQymjRoVA6+YUdk7
cBUww7N/4BUZJzUwl1jOkkPzytYXGpqJZZd9vaF7V8ZVso9gHWuJOXekvR9LhmD7lra/IdFe+zlfW2VR9i+uQjvbOtK3wf7nGsfP
NoQ8qkJ+Zo8Vqlavm1vbQfnXx4+gt+BWrtFLKsmd3fX6oFJJFn3LIugcNbVAZd4qDMajPDwAfkbDPzsAZmA+OwA+RPHfTpmr+l3Z
MCrqifKdpj9Z0e7wsp5W0WNzdJaRVmNfsa/SqshXUJhjNMbX63LECRR6U1lO1vfk9dLyXl6/6mtoyoKBomiHanuNQ3DUnT491Jfo
Kr60WfGZGNNQC37qSiK2q1qJapNfcmuasOTE40tvbv9a5vZ0HVRhL//LFj2P2Lf/nR0tstXy/Kv/D3mp782gyQAA"""


def load_template() -> str:
    encoded = "".join(EMBEDDED_TEMPLATE_B64.split())
    return gzip.decompress(base64.b64decode(encoded)).decode("utf-8")


def validate_csv(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    populated_rows = 0

    for line_number, row in enumerate(csv.reader(text.splitlines()), start=1):
        if not row or all(not field.strip() for field in row):
            continue
        populated_rows += 1
        if len(row) != 5:
            raise ValueError(
                f"Row {line_number} has {len(row)} columns; expected exactly 5."
            )

        cob_date, bu, ccy, delta, var = (field.strip() for field in row)
        try:
            datetime.strptime(cob_date, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError(
                f"Row {line_number} has an invalid CobDate: {cob_date!r}."
            ) from error

        if not bu or not ccy:
            raise ValueError(f"Row {line_number} has an empty BU or CCY.")
        try:
            float(delta)
        except ValueError as error:
            raise ValueError(
                f"Row {line_number} has an invalid Delta value: {delta!r}."
            ) from error

        if var and var.lower() != "null":
            try:
                float(var)
            except ValueError as error:
                raise ValueError(
                    f"Row {line_number} has an invalid VaR value: {var!r}."
                ) from error

    if populated_rows == 0:
        raise ValueError("The CSV contains no data rows.")
    return text


def generate(input_path: Path, output_path: Path) -> None:
    input_path = input_path.resolve()
    output_path = output_path.resolve()

    if input_path == output_path:
        raise ValueError("The output HTML path cannot overwrite the input CSV.")

    csv_text = validate_csv(input_path)
    html = load_template()
    embedded_data = "const SAMPLE_CSV = " + json.dumps(csv_text) + ";"

    # A callback keeps JSON escape sequences literal in JavaScript.
    html, sample_count = SAMPLE_PATTERN.subn(
        lambda _match: embedded_data, html, count=1
    )
    if sample_count != 1:
        raise RuntimeError("Could not locate the embedded-data hook in the embedded template.")

    if FETCH_BLOCK not in html:
        raise RuntimeError("Could not locate the sample-loading hook in the embedded template.")
    html = html.replace(FETCH_BLOCK, "    setData(SAMPLE_CSV, 'Static report');", 1)
    html, label_count = LOAD_LABEL_PATTERN.subn("", html, count=1)
    if label_count != 1:
        raise RuntimeError("Could not locate the CSV loader control in the embedded template.")

    html = html.replace(
        "<!doctype html>",
        "<!doctype html>\n<!-- Self-contained report generated by generate_dashboard.py -->",
        1,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a standalone FX exposure HTML dashboard."
    )
    parser.add_argument("csv_file", type=Path, help="Headerless five-column FX CSV")
    parser.add_argument("-o", "--output", type=Path, help="Output HTML path")
    args = parser.parse_args()

    input_path = args.csv_file
    if not input_path.is_file():
        parser.error(f"CSV file not found: {input_path}")
    output_path = args.output or input_path.with_name(
        f"{input_path.stem}_dashboard.html"
    )

    try:
        generate(input_path, output_path)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(f"Created static dashboard: {output_path.resolve()}")


if __name__ == "__main__":
    main()
