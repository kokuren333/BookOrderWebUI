---
description: 本のデザインを対話で詰める（誌面プルーフを見ながら）
---
skills/design/design-dialogue.md を読み、この本のデザインを私と対話で詰めてください。

0. 参考にすべき書籍を4〜6冊リストアップし（私が挙げた本を優先）、`bookorder delegate design-refs` で公開サンプルページを集め、分析を plan/design-references.yaml にまとめて見せてください。
1. 原稿（plan/book-bible.yaml と代表的な2章）と現在のデザイン（book.design.yaml、テーマ）を読み、方向性を2〜3案、言葉で提案してください。WebUIで選んだテーマや値は出発点にすぎません。
2. 私が選んだ方向で組み、`bookorder proof` で実際の誌面PNGを作り、まず自分で見て直せるところを直してから見せてください。
3. 私の要望（自然言語）を反映して再プルーフ、を繰り返します。やり取りは plan/design-dialogue.md に記録してください。
3b. 生成画像を使う場合は plan/image-style.md を書き、`bookorder images samples` の候補から私とスタイルアンカーを決めてください。
4. 私が「これでOK」と言ったら `bookorder design-approve --user-approval "<私の言葉>"` を実行し、plan/design-decisions.yaml を書いて `bookorder done design` してください。

原稿本文・引用・図表のデータは変更しないでください（必要なら `bookorder revision request`）。

要望: $ARGUMENTS
