# 意味を保った誌面設計と技術書の読みやすさ — Editorial Design for Japanese / English {#ch-design}

::: {.lead}
本文を主体に、情報の種類に応じて見出し、図版、注記を使い分けます。色と書体の階層は説明を助けるために用います。
:::

## 本文と情報の階層 {#sec-hierarchy}

日本語とEnglishを混在させた通常本文です。**重要な語句**と*emphasis*、[参照リンク](https://typst.app/docs/)を含みます。脚注も本文の流れを妨げない位置に配置します。[^detail]

### 長い見出しでも自然に折り返し、本文との関係を失わない設計 {#sec-long-title}

::: {.key-point title="読み手に残す要点"}
意味の構造は出力形式が変わっても維持します。通常本文をカードで埋め尽くしません。
:::

::: {.note title="補足"}
テーマの選択は内容の根拠や意味を変えるものではありません。
:::

::: {.warning title="実行前の注意"}
フォントの利用条件と、公開する資料の再配布権を確認してください。
:::

::: {.definition title="Design Token"}
判型、書体、配色、余白などを、出力先に依存しない値として保持したものです。
:::

> 書籍のデザインは、内容の理解を支える情報の階層です。

## 比較・コード・ベクター図 {#sec-examples}

| 出力 | 役割 | 編集場所 |
|:-----|:-----|:---------|
| PDF | 固定組版 | Design Spec / theme |
| Web | 読者の画面 | CSS / custom.css |
| DOCX | 編集受け渡し | Paragraph styles |

Table: [意味と見た目の分担]{#tbl-preview}

::: {.code-listing title="Python example"}
```python
def publish(book_ir, design):
    return renderer.render(book_ir, design)
```
:::

::: {.terminal-session title="Terminal"}
```text
$ bookorder build --theme modern-technical
Build complete.
```
:::

::: {.full-width-figure}
![Book IRとDesign Specからの出版](source/assets/figures/design-flow.svg){#fig-design}
:::

@fig:design と@tbl:preview は同じ意味構造を共有します。学習の損失は@eq:loss のように番号付きの式として組み、本文中の $p_\theta(x)$ のような数式も文字として保持します。

::: {.equation #eq-loss}
$$\mathcal{L}(\theta) = -\frac{1}{N}\sum_{i=1}^{N} \log p_\theta(x_i) + \lambda \lVert \theta \rVert_2^2$$
:::

長いURLも表示できます：<https://example.org/documentation/very-long-reference-path/editorial-design/semantic-content-and-design-spec>。

::: {.summary title="章のまとめ"}
- 内容とデザインを分離する。
- 出力ごとの特性を尊重する。
- 自動チェックと視覚確認を組み合わせる。
:::

[^detail]: 小さい文字の可読性もプレビューで確認します。

## 参考文献 {#sec-references .unnumbered}

変換の例はPandocの公式文書を参照します [@pandoc]。
