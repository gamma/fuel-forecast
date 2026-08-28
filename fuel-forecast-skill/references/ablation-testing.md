# Model ablation testing

Run:

```sh
python3 /var/minis/skills/fuel-forecast/scripts/ablation_backtest.py \
  --checkpoints 50,100,120,130,140 --evaluation-days 10
```

The command compares four expanding-window variants on identical unseen dates:

1. local price dynamics and weekday only;
2. local plus symmetric Brent/distillate changes in USD;
3. local plus symmetric Brent/distillate changes converted to EUR;
4. local plus EUR market inputs and asymmetric rockets-and-feathers features.

All variants are compared with an unchanged-price baseline. Output is written to
`memory/ablation_report.json`.

## Historical news limitation

Historical news is deliberately zero in every variant. There is no point-in-time
archive containing exactly the articles available before each historical 07:00
run plus a frozen residual-news score. Retrospective GPT research could leak
later knowledge and would overstate performance.

News can materially affect fuel prices during sanctions, refinery outages,
export restrictions, shipping disruptions, and policy surprises. However, the
portion already reflected in Brent or distillate futures must not be counted a
second time. The live workflow therefore treats news only as a residual shock.
