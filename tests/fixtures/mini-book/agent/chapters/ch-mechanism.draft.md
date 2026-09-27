# 自己注意とTransformer {#ch-mechanism}

## スケール化内積注意 {#sec-mechanism-scaled}

@ch:foundations で見た文脈ベクトルの考え方を、別の系列ではなく同じ系列内のすべての位置の間に適用したものが自己注意である。2017年に提案されたTransformerは、再帰的な構造を使わずに自己注意だけで系列を処理するため、前の時点の計算を待たずに全位置を並列に計算できる [cite:{{src:transformer-architecture}}]。

計算の中心はスケール化内積注意であり、問い合わせ行列 $Q$、鍵行列 $K$、値行列 $V$ から @eq:attention のように出力を得る。

::: {.equation #eq-attention}
$$\operatorname{Attention}(Q, K, V) = \operatorname{softmax}\left(\frac{QK^{\top}}{\sqrt{d_k}}\right) V$$
:::

問い合わせと鍵の内積は両者の適合度を表す。これを鍵の次元 $d_k$ の平方根で割るのは、次元が大きいと内積の値が大きくなり、ソフトマックス関数の出力が一点に集中して勾配が極端に小さくなるのを防ぐためである [cite:{{src:transformer-architecture}}]。正規化された重みで値を加重平均する点は、@sec:foundations-idea で説明した文脈ベクトルと同じである。計算の流れを@fig:attention-flow に示す。

![スケール化内積注意の計算の流れ](source/assets/figures/attention-flow.svg){#fig-attention-flow}

## マルチヘッド注意と位置 {#sec-mechanism-multihead}

一つの注意だけでは、構文的な依存関係と近傍の語との関係のように、性質の異なる関係を同時に捉えにくい。マルチヘッド注意は、問い合わせ・鍵・値をそれぞれ複数の低次元空間に線形射影し、各空間で独立に注意を計算してから結合する [cite:{{src:transformer-architecture}}]。ヘッドごとに異なる関係を捉える分業が観察されることもあるが、その役割は学習の結果として現れるものであり、設計時に割り当てられるわけではない。

自己注意そのものは入力の順序を区別しない。語順を入れ替えても、各位置の間の適合度の集合は変わらないからである。そこで各位置の表現に位置エンコーディングを加え、順序の情報を与える。原論文では周波数の異なる正弦波と余弦波を組み合わせた固定の符号化が使われたが、後の研究では学習可能な位置埋め込みや、相対位置を扱う方式も広く使われている [cite:{{src:transformer-architecture}},{{src:history}}]。

## 計算量と効率化 {#sec-mechanism-cost}

自己注意の計算量は系列長の二乗に比例する [cite:{{src:transformer-architecture}}]。
