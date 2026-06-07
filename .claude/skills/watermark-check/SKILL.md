---
name: watermark-check
description: >-
  Verification checklist for any change to this project's watermark code. Trigger
  whenever you edit, review, or debug watermark logic in tools/word_watermark.py,
  tools/word_to_image_pdf_watermark.py, or tools/pdf_to_images_pdf.py — anything
  touching font size, alignment, multi-line/tiled layout, rotation, shape sizing,
  or VML/PDF rendering of watermarks. Use this BEFORE declaring a watermark change
  done. Does NOT apply to non-watermark tools.
---

# 水印改动验收 (watermark-check)

本项目的水印逻辑反复踩坑（字号、对齐、Word 多行、整体旋转）。任何水印改动在收尾前，**必须**走完下面两步：先跑测试守住不变量，再做视觉验收。

## 三个水印出口

水印分散在三处，改一处时想清楚另外两处是否也要同步：

| 文件 | 场景 | 关键实现 |
|------|------|----------|
| `tools/word_watermark.py` | Word 文档直接加水印 | VML `<v:shape>` + XML |
| `tools/word_to_image_pdf_watermark.py` | Word → 图片型 PDF 加水印 | 渲染后叠加 |
| `tools/pdf_to_images_pdf.py` | PDF → 图片型 PDF 加水印 | `_rendered_text_font_size`（渲染缩放） |

## 第 1 步：跑测试（守不变量）

```bash
python -m pytest tests/test_watermark_font_size.py -v
```

这个测试文件固化了所有踩过的坑，**改动后它必须全绿**。它守住的核心不变量：

- **默认字号 = 72**（三个对话框统一）。
- **CJK 字接近方形**：水印框 `width ≈ 字数 × height`（修过"被压成瘦长"的 bug）。
- **VML 字号 ≠ 输入字号**：`_vml_text_font_size(96) <= 24` 且随输入单调递增。
- **PDF 渲染缩放 2×**：`_rendered_text_font_size(96) == 192`（图片型 PDF 是放大渲染的，字号要乘缩放）。
- **多水印 = 单段落 + 多独立 shape**：`<w:p>` 只出现 1 次（避免多余空行/回车），但 `<w:pict>` / `<v:shape>` 按数量出现，spid 各不相同。
- **绝对定位、禁用 center**：必须 `mso-position-horizontal:absolute`，绝不能出现 `:center`（否则全挤到正中重叠）。
- **整体绕页心旋转**：平铺阵列是整体旋转，相邻水印偏移 = 旋转后的基向量，且旋转后基向量不平行于坐标轴。

> 如果你新增了行为，**先加/改测试再改实现**（项目 AGENTS.md 要求改业务逻辑后跑 pytest）。

## 第 2 步：视觉验收（测试覆盖不到的）

测试只能验 XML/数值，**实际渲染效果必须用眼睛看**。

- **用 4 个字的样本验收**：固定用 `环聚医药`（4 字 CJK），**不要**用 2 字的 `水印`。2 字看不出宽高比、间距、平铺密度的问题，4 字才能暴露真实排版。
- 通过 GUI 实跑一遍受影响的出口（`python main.py` → 对应工具），或直接调用对应函数生成一份真实输出文件后打开查看。
- 重点看：① 字号视觉合理；② CJK 不被拉瘦/压扁；③ 多行/平铺不重叠、不挤中间；④ 旋转角度一致、铺满整页；⑤ Word 文档里没有多出来的空行。

## 收尾报告

说明：改了哪个出口、其余两个是否需要同步、pytest 结果、以及用 `环聚医药` 做的视觉验收结论（最好附生成的样张路径）。
