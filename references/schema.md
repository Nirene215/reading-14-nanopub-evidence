# 字段字典（v1.0）

本格式是证据可追溯 JSON 账本，不等同于正式 RDF Nanopublication 标准。科学含义、原子性、蕴含关系由 Agent 核阅；脚本只校验可确定的文件、位置、字段和引用约束。JSON 必须是 UTF-8，不含 NaN/Infinity。

## corpus.json：实际文件抽取索引

由 `prepare` 创建，禁止手工修改。顶层 `schema_version`、`tool_version`、`sources`、`notes`。

| 字段 | 类型与含义 |
| --- | --- |
| sources[].source_id | `src-` 前缀的确定性标识，结合当前绝对路径和文件哈希；路径变化需要重新 prepare/rebind |
| path / sha256 | 实际绝对路径 / SHA-256；缺失文件 hash 为 null |
| status | `ready`、`needs_ocr`、`missing`、`unreadable`；ready 只表示可抽取文本，不表示版式或语义正确 |
| parser | 实际解析器及版本，未执行为 null |
| metadata | 默认 title/year/doi/version=null、authors=[]；禁止从文件名猜元数据 |
| diagnostics | 实际读取错误及已知抽取限制 |
| segments[] | 当前解析器产生的文本片段，保留内部换行和空白 |
| segment_id | 源文件内唯一；PDF 例如 p0003-b0002，纯文本 p0000-b0001 |
| page | 实际 PDF 物理页，从 1 起；TXT/MD 为 null，绝不能将 0 当作原文页码 |
| paragraph | 当前页解析段落序号，从 1 起；不是出版社段落编号 |
| kind / text | 当前实现 kind=text；text 为精确匹配的字符串 |
| page_count / empty_pages | PDF 总页数 / 无可抽取文本的物理页列表；可能是空白页，也可能需要 OCR，须人工判断 |

`verify` 会重新读取原文件并比较哈希和抽取内容；改动 corpus 中的文字、页码、状态不能代替原文读取。

## candidate.json：Agent 实际阅读后的工作稿

| 顶层字段 | 必需与定义 |
| --- | --- |
| case_id | 必需，原始案例标识，不自行改名；无正式案例的演示须明确写 demo 标识 |
| task_summary | 必需，说明实际任务与材料范围 |
| status | 必需，`success` / `partial` / `cannot_determine` / `refused` / `failed` |
| assertions | 必需，断言对象数组；全程无法判断可为空，此时不能 success |
| evidence | 必需，精确证据数组；没有证据可以为空，但不得声称断言直接被支持 |
| coverage | 必需且非空，逐一映射真实任务要求及实际处理结果 |
| uncertainty | 必需，数组，无不确定项可为空；非 success、未解决冲突、材料失败必须说明 |
| change_log | 必需且非空，实际改动及理由；首次创建也应记录 |
| source_metadata | 可选，来自实际原文的元数据补充数组 |
| contract_result | 有正式 output_contract 时必需，Agent 按该合同实际填写的全部原字段对象 |

`success`：所有任务覆盖，关键断言有支撑，实际材料可读，无未解决冲突；不代表经过正式测评分数认证。
`partial`：交付已核实部分并指出剩余问题；`cannot_determine`：材料不足，无法得出所需判断；`failed`：实际执行失败；`refused`：实际任务范围不能执行，说明原因。脚本允许诚实 partial 通过结构检查，不将其升级为 success。

### 断言对象

| 字段 | 定义 |
| --- | --- |
| assertion_id | 非空唯一字符串，供覆盖、证据和后续复用引用 |
| text | 一个可独立判断的断言，保留科学限定条件；不能复制整段摘要作为断言 |
| subject / relation / object | 主体、关系、客体；复杂数字/单位可写入 object 和 qualifiers，但 text 必须自足 |
| relation_label | relation=other 时必填，对实际关系命名 |
| polarity | positive / negative / uncertain；未检出显著差异不等于确定无效 |
| qualifiers | 必需对象；保留原文 population、comparator、time、conditions、unit、uncertainty、modality 等。可以为空，但不能据此删除原文条件 |
| support | direct / inferred / contradicted / insufficient；direct 为原文直接支持，不能只因字符串出现就选 direct |
| evidence_ids | 全部相关 evidence_id，含必要前提、反证和上下文；同一证据可支持多个独立断言 |
| derivation | inferred 必填，明确从哪些前提推到哪些结论；不是对原句的随意改写 |
| confidence | 对象，level=high/medium/low/undetermined，basis 为具体依据；不伪造校准概率。high 只用于条件齐全的直接证据 |
| review | 对象，atomic=true、scope_checked=true、entailment=supports/contradicts/unclear、rationale 为具体核阅理由。不要把占位 true 当实际核阅 |

受控关系：`reports`、`compares`、`associated_with`、`increases`、`decreases`、`no_detected_difference`、`causes`、`improves`、`worsens`、`measures`、`uses`、`predicts`、`supports`、`contradicts`、`other`。无足够因果证据时，相关性使用 associated_with，不选择 causes。

qualifiers 的键不强制统一，但建议样本量用 `sample_size`（整数）并另列 `population`，关联量用 `association_coefficient`，原文报告的系数类型用 `coefficient_type`。原文只有 r 时不可猜成 Pearson 或 Spearman；省略类型或用 null 并说明边界。未复现可使用 `other` + `relation_label=replicated_in` + `polarity=negative`，在 text 中明确“未复现”，不能改为“真实效应为零”。

结构校验只阻止**精确结构重复**（text、主体、关系、客体、极性、条件、支撑类型相同），不会语义去重。Agent 合并语义重复时须保留全部证据；不同来源、版本、方向、时间或群体有差异应分别保留。

### 证据对象

```json
{
  "evidence_id": "e1",
  "source_id": "复制自实际corpus",
  "segment_id": "p0001-b0001",
  "start": 10,
  "end": 20,
  "quote": "须精确等于text[10:20]",
  "role": "supports"
}
```

以上仅说明结构，不是可运行证据。使用 `locate` 查真实片段。start/end 是 **Unicode 字符索引、0 起、左闭右开**；不是 UTF-8 字节或 JavaScript UTF-16 单元。不得擅改连字符、空格、换行、大小写。role 为 supports、contradicts、context；context 本身不能满足断言的支持要求。可额外加 page（必须与 segment 一致）、printed_page、section、figure、table 等真实可核对的定位提示。跨页证据必须拆成多个记录，不伪造跨页引文。

### coverage / uncertainty / change_log

```json
{
  "coverage": [{
    "requirement": "真实任务的一项要求",
    "status": "covered",
    "assertion_ids": ["a1"],
    "evidence_ids": ["e1"],
    "reason": "说明该结果如何覆盖该项要求"
  }],
  "uncertainty": [{
    "code": "cannot_determine",
    "message": "明确缺口、影响、原文位置和人工接管操作",
    "assertion_ids": []
  }],
  "change_log": [{"change": "本次实际创建或修订", "reason": "依据"}]
}
```

coverage.status 可取 covered、partial、not_reported、cannot_determine、material_missing、execution_failure。covered 至少关联一个断言；引用必须存在。uncertainty.code 使用明确原因，如 not_reported、cannot_determine、material_missing、execution_failure、conflict、ocr_unavailable；message 必需，其他定位/引用字段按需补充。未报告是已检查原文后的结论；无法判断是证据范围或可访问性不足。两者分开记录。

### 来源元数据

source_metadata 数组每项包含 source_id、title、authors（字符串数组）、year、doi、version、metadata_evidence（本来源的证据 ID 数组）。未报告值使用 null/[]。非空元数据必须有原文证据。记录清楚作者顺序、预印本/期刊版或修订日期；脚本无法判断一段引文是否真的蕴含这些元数据，Agent 需要核对。不要把文件修改时间当论文发表年份。

## 导出与正式 output_contract

无正式合同：`result.json` 为规范账本，包含 case_id、status、task_summary、assertions、evidence、sources、coverage、uncertainty、change_log、validation、schema_version。sources 保留原文件路径/哈希/解析器、元数据和 segment_index（页/段定位），不重复整篇原文。

有正式合同：Agent 将实际任务输出填进 contract_result。`finalize --case` 只做可确定的结构检查及 case_id 一致性检查，正式字段原样导出到 result.json；证据账本与校验记录另外保存为 nanopublications.json、validation.json。正式 status 如使用本技能定义的值，必须和规范账本一致；不能把 partial 导出为 success/completed/ok。任意自定义字段的科学含义和状态编码映射仍需 Agent 检查。

合同解析支持：JSON Schema 的 type、properties、required、items、enum、const、additionalProperties、minItems/maxItems、minLength/maxLength、minimum/maximum；type 支持 union 数组。$schema/$id/title/description/examples/default 为注释。也支持字符串字段列表、含 name 的字段对象列表、普通“字段名:说明”映射。**不声称完整 JSON Schema 实现**；$ref、oneOf、pattern 等未支持语法会明确拒绝。遇到这种情况应采用平台实际完整验证器，按实际合同人工导出并保留本助手的错误记录/规范账本，不能删除原约束来制造通过。

验证失败时，退出码 2，result.json 是 partial/cannot_determine 恢复文档；原 contract_result 如存在保存在 unvalidated_contract_draft 中。不得把恢复文档冒充已符合正式合同。CLI 错误会向 stderr 输出 JSON，不吞掉失败。

## 维护边界

相同文件、相同解释器/解析器版本产生稳定本地索引；换机器路径或解析器版本后须重新 prepare 并核对引用。输出记录只保存真实执行数据，不自动产生平台 trace、模型调用数、正式评分或性能增益结论。文本资源与脚本可脱离本机使用；本机环境详情位于项目 README，平台路径不得依赖本机绝对路径。
