# 最小调用示例：完全合成，不是正式案例答案

source.txt 是专为演示写的虚构文本，包含两个结论；make_candidate.py 仅为这个文本构造教学候选，不是自动科研抽取算法。真正案例须由 Agent 阅读实际论文后生成 candidate.json，不得调用这个演示生成器当作正式抽取器。

从 submission 所在项目根目录运行（将 python 换成实际可用的 Python 3.10+）：

```sh
python submission/scripts/nanopub.py prepare --source submission/examples/source.txt --out work/demo/corpus.json
python submission/examples/make_candidate.py --corpus work/demo/corpus.json --out work/demo/candidate.json
python submission/scripts/nanopub.py verify --corpus work/demo/corpus.json --candidate work/demo/candidate.json --out work/demo/check.json
python submission/scripts/nanopub.py finalize --corpus work/demo/corpus.json --candidate work/demo/candidate.json --out output/demo/result.json
```

若已在 submission 目录内，去掉各路径开头的 submission/，将工作/输出路径指向提交目录之外。Harbor 正式运行时使用绝对安装路径，见 SKILL.md。

示意输出（仅节选结构，实际定位值由本机真实读取计算）：

```json
{
  "case_id": "DEMO-SYNTHETIC-ONLY",
  "status": "success",
  "validation": {
    "valid": true,
    "counts": {"sources": 1, "assertions": 2, "evidence": 2}
  }
}
```

实际输出还包含断言、精确引文、文件哈希和来源页段索引。finalize 同时保存 nanopublications.json 和 validation.json。输出仅说明助手接口在合成文本上可运行，不表示真实科研正确性、正式案例完成度或对基线的增益。

可修改副本中的 quote 再运行 verify，确认错引文会退出 2。修改原文后须重新 prepare/rebind；验证会拒绝旧哈希及篡改后的 corpus。所有生成文件都放在提交目录之外。
