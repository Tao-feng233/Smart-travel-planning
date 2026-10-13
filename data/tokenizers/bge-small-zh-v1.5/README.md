# BGE 中文 Tokenizer

此目录只包含分词器，不包含 ONNX 模型权重。知识资料切分及 BM25 检索不需要加载嵌入模型权重，也不需要联网下载。

- 模型：`BAAI/bge-small-zh-v1.5`
- 文件来源：FastEmbed 使用的 [Qdrant/bge-small-zh-v1.5](https://huggingface.co/Qdrant/bge-small-zh-v1.5)，修订 `46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59`。
- 原始模型及许可证说明：[BAAI/bge-small-zh-v1.5](https://huggingface.co/BAAI/bge-small-zh-v1.5)（MIT）。
- 本文件与本机正在使用的 FastEmbed 模型缓存中的 `tokenizer.json` 一致。

计数时禁用截断和补齐；推理时 FastEmbed 使用自己的实例，不修改其配置。父块上限 1400 个 BGE Token；子块的完整索引输入上限 360 个 BGE Token（包含城市、标题前缀和特殊标记），相邻子块尽量保留 50 Token 重叠。切分优先保留句子边界，过长单句按原文字符位置切开，不解码 Token 重建正文。

如果更换切分用的分词器，须同步更新来源、模型身份及文件；分词器指纹参与语料版本，旧向量索引须重建。父块不是 BGE 的嵌入输入，提供给生成模型时仍受检索总上下文预算限制。
