---
description: 出版ジョブを最後まで実行する（Claudeが統括、調査はCodexに委譲）
---
CLAUDE.md と AGENTS.md を読み、`bookorder goal` が `STATUS: COMPLETE` を表示するまで出版ジョブを実行してください。

- 資料は私が全部渡していなくて構いません。調査要件（project.json research.requirements）と本の目的から plan/research-brief.md を書き、Codexに一次情報・信頼できる二次情報を探させてください。事実の根拠（evidence）と一般的な知見の参考資料（background）を区別し、巻末の引用文献には本文で引用したevidenceだけを載せてください。
- 調査系タスク（ingest: / verify: / research: / analyze:）、章ごとのエビデンスマップ、ファクトチェックは `bookorder delegate` で Codex CLI に委譲し、結果を自分でレビューしてから `bookorder done` してください。時間がかかる委譲はバックグラウンドで実行し、その間に独立した作業を進めてください。
- 執筆はあなたが行います。skills/authoring/voice.md に従い、エビデンスの強さに見合った断定で書いてください。
- デザイン工程（design タスク）では作業を止めて私と対話してください。参考書籍のリストアップとサンプルページ収集（`bookorder delegate design-refs`）→ 方向性の提案 → `bookorder proof` の誌面画像 → 私のフィードバック → 修正、を承認まで繰り返します。生成画像を使う場合は画像スタイルシートとスタイルアンカーを決めてから生成してください。
- 途中で「続けますか？」とは聞かないでください。止まるのはデザイン対話・本当のブロッカー・ページ数や範囲の変更が必要なときだけです。

$ARGUMENTS
