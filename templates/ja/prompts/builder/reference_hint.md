## 共有リファレンス（reference）

参照用の共有ドキュメントが蓄積されている。仕様書・APIリファレンス・規約など、読み取り専用の参照資料。
調べるときは reference を read_memory_file で参照すること。書き込みは不可（common_knowledge を使用）。

- 読む: `read_memory_file(path="reference/...")`
- 書き込み: 不可（reference/ は読み取り専用）
