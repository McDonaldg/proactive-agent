# proactive-agent

週3回（月・水・金）、3 枚の提案カードをスライド画像として Discord に出し、
リアクションと返信から学習する。

## 全体の流れ

```
[collect.py]  RSS + YouTube RSS + HN      LLM なし
     ↓ data/pool.jsonl
[propose.py]  スコア上位20 → カード3枚     Sonnet 5 x1
     ↓ src/lib/slide.py でスライド画像(PNG)化
     ↓ Discord に画像添付で投稿 + 絵文字を先置き
   （人間: 絵文字を押す / 返信で要望を書く）
     ↓
[feedback.py] タグ回収 → 重み補正          Haiku x 返信数
              返信分類 → interests.jsonl
```

## セットアップ

1. Discord に **Bot** を作る（Webhook では不可）
   - 権限: Send Messages / Read Message History / Add Reactions
   - Message Content Intent を ON にしないと返信本文が読めない
2. GitHub の Secrets に登録
   - `ANTHROPIC_API_KEY`
   - `DISCORD_BOT_TOKEN`
   - `DISCORD_CHANNEL_ID`
3. `config/feeds.yaml` の YouTube `channel_id` を実際の値に置換
4. `config/profile.json` の初期重みを自分の感覚で調整
5. Actions タブから `daily-proposal` を手動実行して疎通確認

配信は `.github/workflows/daily.yml` の cron で週3回（月・水・金 07:00 JST）に
設定済み。頻度を変える場合はここの cron 式を変更する。

## モデル使い分け（src/lib/llm.py に集約）

| 工程 | モデル | 理由 |
|---|---|---|
| 収集・スコアリング | なし | ルールで足りる。ここで課金したら設計が負け |
| 自由入力の分類 | Haiku 4.5 | 出力が短く判断基準が明示的 |
| カード本文の生成 | Sonnet 5 | ここだけ品質が体験に直結する |
| 実行層 | Sonnet 5 / 設計判断を含むときのみ Opus 5 | 定期実行の中では Opus を使わない |

## 状態ファイル

| ファイル | 中身 | 増え方 |
|---|---|---|
| `data/pool.jsonl` | 収集記事 | 日次。21日で剪定推奨 |
| `data/proposals.jsonl` | 提案カード履歴 | 日 1 行 |
| `data/decisions.jsonl` | 承認/否認タグ | 日 1 行 |
| `data/interests.jsonl` | 自由入力キュー | 不定期 |
| `data/usage.jsonl` | LLM トークン消費 | 呼び出しごと |

## 設計上の決めごと

- **枠は固定**。指名枠は必ず 1 枠まで。全枠をリクエストで埋めると
  「自分では思いつかなかった提案」が消え、ただの検索窓になる。
- **否認履歴は全文を渡さない**。タグの集計文字列だけを渡す。
- **指名枠は 3 回で自動クローズ**し、必ず Discord で報告する。
  黙って消えるのが最も信頼を失う。
- **同時実行を禁止**（concurrency）。JSONL の追記が競合すると壊れる。

## 既知の弱点

- スコアリングが単純なキーワードマッチ。既存の M1 パイプラインに
  embedding 選抜があるなら `propose.py:score()` だけ差し替えると精度が上がる。
- 実行層（承認 → PR 生成）はまだ入っていない。②が回ってから追加する。
