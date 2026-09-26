"""실제 .env를 처음 한 번 생성합니다. 기존 설정은 덮어쓰지 않습니다."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print("기존 .env를 보존했습니다.")
else:
    content = (root / ".env.example").read_text(encoding="utf-8")
    content = content.replace("POSTGRES_PASSWORD=\n", f"POSTGRES_PASSWORD={secrets.token_hex(32)}\n")
    with target.open("x", encoding="utf-8", newline="\n") as output:
        output.write(content)
    print(".env 생성 완료. 비밀번호는 화면에 출력하지 않았습니다.")
