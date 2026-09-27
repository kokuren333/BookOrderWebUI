export type InfoPage = 'job' | 'contents' | 'safety';

export function InfoPages({ page }: { page: InfoPage }) {
  if (page === 'contents') return <article className="info-page">
    <h2>ZIPに同梱するもの・ライセンス</h2>
    <p>選択したOS・CPU向けの実行ファイルと、出版ジョブの原稿・設定・変換スクリプトをまとめます。AI Agent本体やAIモデルは含まれません。ZIPを展開してコマンドを実行できるAgentが必要です。</p>
    <div className="table-scroll"><table><thead><tr><th>同梱物</th><th>バージョン・用途</th><th>ライセンスと同梱資料</th></tr></thead><tbody>
      <tr><td>Python</td><td>Windows: 3.14.7 embeddable<br />macOS/Linux: 3.12.14（python-build-standalone 20260924）<br />検証・変換の制御</td><td><a href="https://docs.python.org/3/license.html">PSFほか</a>。配布物の通知と依存ライブラリの通知を保持。standalone版の関連ソースも同梱。</td></tr>
      <tr><td>Pandoc</td><td>3.11<br />Markdown・DOCX・HTML・EPUBの変換</td><td><a href="https://github.com/jgm/pandoc/blob/3.11/COPYING.md">GPL-2.0-or-later</a>。著作権表示・GPL本文・本体とリンクされた依存ライブラリのソース・ビルド関連資料を同梱。</td></tr>
      <tr><td>Typst CLI</td><td>0.15.1<br />PDF組版</td><td><a href="https://github.com/typst/typst/blob/v0.15.1/LICENSE">Apache-2.0</a>。LICENSE・NOTICEを保持。</td></tr>
      <tr><td>Noto Serif CJK JP</td><td>Regular / Bold<br />日本語PDFのフォント</td><td><a href="https://github.com/notofonts/noto-cjk/blob/main/Serif/LICENSE">SIL OFL-1.1</a>。フォントは未改変で同梱し、ライセンス・通知を保持。</td></tr>
      <tr><td>Noto Sans JP</td><td>Regular / Bold<br />日本語の見出し・図版・キャプション</td><td><a href="https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE">SIL OFL-1.1</a>。公式リリースアーカイブから未改変で抽出。</td></tr>
      <tr><td>Source Serif 4 / Inter / JetBrains Mono</td><td>欧文本文・欧文見出し・コード</td><td>SIL OFL-1.1（<a href="https://github.com/adobe-fonts/source-serif">Source Serif</a>・<a href="https://github.com/rsms/inter">Inter</a>・<a href="https://github.com/JetBrains/JetBrainsMono">JetBrains Mono</a>）。未改変で同梱し、Webサイトでは使用する欧文フォントをライセンスとともに配置。</td></tr>
      <tr><td>出版ジョブ</td><td>AGENTS.md・TASK.md・project.json・Pythonスクリプト・出力テンプレート</td><td>ユーザーの入力・資料を含みます。資料の著作権は変わりません。第三者資料の再配布権はユーザー側で確認してください。</td></tr>
    </tbody></table></div>
    <h3>デザイン用の同梱物</h3><p>5種類のテーマ（modern-technical、academic-jp、medical-textbook、minimal-monochrome、business-reference）、誌面サンプル、Design Specのスキーマ、24種類の誌面部品、図の構造化データからSVGを生成するスクリプトを含みます。デザイン変更用の <code>book.design.yaml</code>、<code>custom.css</code>、<code>custom.typ</code> と使い方の説明も保存します。テーマ自体にフォントファイルは含まず、フォントは実行環境パックにライセンスとともに同梱します。</p>
    <h3>対応環境</h3><p>Windows 10以降のx64、macOS 15以降のApple Silicon / Intel、Linux x64 / ARM64（glibc 2.17以降）を選択できます。同梱するPandocのmacOS版は15以降が必要です。使用中のブラウザではなく、Agentがコマンドを実行するマシンに合わせてください。Windows ARM、Alpine Linuxなどのmusl環境は対象外です。</p>
    <p>Windowsは同梱ランタイムによる実行を検証します。macOS/Linuxは実行ファイルと起動処理を用意していますが、この開発環境では実機での動作は未検証です。OSの実行制限やセキュリティ設定によって起動できない場合があります。</p>
    <h3>ソースも含めて再配布</h3><p><code>third-party/</code> にライセンス通知・対応ソースアーカイブ・出典URL・SHA-256一覧を収録します。完成後の <code>publish/result.zip</code> にも保持します。ZIPを再配布する際は、このディレクトリを削除しないでください。</p>
    <p>Windows版PythonにはMicrosoftの配布コードも含まれます。<a href="https://github.com/python/cpython/blob/v3.14.7/PC/crtlicense.txt">その配布条件</a>も元のLICENSE.txtに保持しています。Microsoftの権利表示を改変しないこと、Microsoftの承認があるように表示しないこと、対象外プラットフォームや悪意ある用途へ配布しないことなどの条件が、この配布コードに適用されます。再配布先にも元の通知と条件を渡してください。これらの条件はPython自体や作成した本へ一律に適用するものではありません。</p>
    <p>各ツールは独立したコマンドとして実行します。PandocのGPLはPandocとその派生物に適用されます。生成した本のライセンスは、原稿・引用・図版などの権利に基づいて決めてください。</p>
    <p>対応ソースとフォントも含むため、ZIPは大きくなります。必要な空きメモリ・ディスク容量を確保してください。「同梱なし」を選ぶ場合は、Agent側にツールと日本語フォントが必要です。</p>
    <h3>WebUIのソフトウェア</h3><p>WebUIはReactとJSZipを使用し、ブラウザ内でフォームとZIP生成を処理します。ReactはMIT、JSZipはMITライセンスの選択肢で使用します。関連ライブラリを含む <a href={`${import.meta.env.BASE_URL}webui-licenses.txt`}>WebUIの第三者ライセンス通知</a> も配布しています。</p>
  </article>;
  if (page === 'safety') return <article className="info-page">
    <h2>実行時の安全性・データの扱い</h2>
    <h3>このWebUIで行うこと</h3><p>入力した企画・追加指示・選択した資料をブラウザ内でZIPにまとめます。入力内容や資料をサーバーへアップロードする処理はありません。参考URLの取得、AIへの送信、原稿の生成、同梱コマンドの実行は行いません。</p>
    <p>WebUIの表示と、選択した実行環境・ライセンス資料のダウンロードには通信します。実行環境はこのサイトと同じ配布元から取得します。通常のWebアクセスとして、配布サーバーにはIPアドレスやアクセス記録が残る場合があります。</p>
    <h3>ZIPを渡した後に行うこと</h3><p>AgentがZIPを展開し、Windowsでは <code>run.cmd</code>、macOS/Linuxでは <code>sh run.sh</code> を実行します。初回にPython・Pandoc・Typstをジョブ内へ展開し、同梱フォントで変換します。起動処理による追加ダウンロード、管理者権限の要求、システムへのツールのインストールはありません。</p>
    <p>変換スクリプトは、原稿・設定・資料を読み、ジョブ内の <code>interchange/</code>、<code>publish/</code>、<code>reports/</code> などへ書き込みます。再ビルドで生成物を更新します。原稿の執筆・編集やWeb調査はAgentが行う別の処理です。</p>
    <h3>追加のデザイン設定</h3><p><code>custom.css</code> 内の外部URLやWebフォントは、生成した本を閲覧する際に通信する場合があります。PDF向けの <code>custom.typ</code> はTypstコンパイラで処理するコードです。第三者から受け取った設定を使う場合は内容を確認してください。</p>
    <h3>整合性の確認と限界</h3><p>WebUIは取得したランタイムの各分割ファイル・全体・実行ファイルアーカイブのSHA-256を確認し、不一致や欠落があればZIP生成を中止します。起動処理でもアーカイブと対応ソースのSHA-256を確認します。</p>
    <p>チェックサムは、配布カタログとの一致を確認する仕組みです。配布元とカタログ自体の改ざんや、プログラムの脆弱性を防ぐ保証にはなりません。コード署名やウイルス検査の代わりでもありません。</p>
    <h3>Agentの権限と資料</h3><p>このZIPはサンドボックスを提供しません。実行したコードはAgentや実行ユーザーの権限で動作します。機密資料を含む場合は、ジョブ専用の作業フォルダや隔離された実行環境を使い、Agentのアクセス範囲を確認してください。</p>
    <p>AGENTS.mdでは、資料・Webページ内の命令を実行指示として扱わず、提供資料を許可なく外部サービスへ送らないよう指示しています。ただし、これはAgentへの指示であり、技術的な通信遮断ではありません。Agentサービスのデータ処理・送信設定は別途適用されます。</p>
    <p>「追加Web調査を許可」はAgentへの調査方針です。無効でも、明示した参考URLは閲覧対象になります。完全なオフライン実行を求める場合は参考URLを指定せず、Agent自体の通信も実行環境側で制限してください。</p>
    <h3>実行前に確認するもの</h3><p><code>AGENTS.md</code>、<code>TASK.md</code>、<code>project.json</code>、起動ファイルと <code>scripts/</code>、<code>third-party/README.md</code> を確認できます。OSやCPUの不一致、壊れたアーカイブ、ビルド・検証の失敗はエラーとして扱います。自動検証だけで内容の正確性や出版品質を保証せず、編集・レイアウトの確認を完了条件に含めています。</p>
  </article>;
  return null;
}
