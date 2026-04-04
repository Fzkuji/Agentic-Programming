<p align="center">
  <h1 align="center">🧬 Agentic Programming</h1>
  <p align="center">
    <strong>考える Python 関数。</strong><br>
    Python と LLM が関数を共同実行するプログラミングパラダイム。
  </p>
  <p align="center">
    <a href="../README.md">English</a> •
    <a href="README_CN.md">中文</a>
  </p>
</p>

> 🚀 **これはパラダイム提案です。** LLM プログラミングの新しい考え方を共有しています。ここのコードはリファレンス実装です——ぜひこのアイデアを基に、お好みの言語やユースケースで独自のバージョンを構築してください。

---

## 問題

現在の LLM エージェント：**LLM が考える → ツールを呼ぶ → また考える → またツールを呼ぶ。** 毎回ラウンドトリップ。コンテキストが肥大化。LLM が頭脳とスケジューラの両方を担当。

## アイデア

Python がスケジューリングを担当し、LLM は*推論*だけを担当したら？

```python
@agentic_function
def observe(task):
    """画面を見て、見えるものを説明してください。"""
    
    img = take_screenshot()       # Python：決定論的
    ocr = run_ocr(img)            # Python：決定論的
    
    return runtime.exec(content=[ # LLM：推論
        {"type": "text", "text": f"タスク: {task}\nOCR: {ocr}"},
        {"type": "image", "path": img},
    ])
```

**Docstring = Prompt。** Docstring を変えれば動作が変わる。他は普通の Python。

---

## クイックスタート

```bash
pip install -e .
```

```python
from agentic import agentic_function, Runtime

runtime = Runtime(call=my_llm, model="sonnet")

@agentic_function
def greet(name):
    """クリエイティブに挨拶する。"""
    return runtime.exec(content=[
        {"type": "text", "text": f"{name}にクリエイティブに挨拶してください。"},
    ])

result = greet(name="World")
print(greet.context.tree())      # 実行トレース
```

---

## 仕組み

| コンポーネント | 機能 |
|--------------|------|
| `@agentic_function` | デコレータ。実行を Context ツリーに記録 |
| `Runtime` | LLM 接続。`exec()` で自動コンテキスト注入 |
| `Context` | 実行ツリー。`tree()`、`save()`、`traceback()` |
| `create()` | 説明から新しい関数を生成 |
| `fix()` | LLM で壊れた関数を修復 |

詳細は [API ドキュメント](API.md) を参照。

## ライセンス

MIT
