---
uid: 4e9b1c63
id: seabreeze-inspector.research-ops.docx-export
parent: seabreeze-inspector.research-ops
tags: [research, docx]
name: {zh: "Markdown→DOCX 导出", en: "Markdown to DOCX Export"}
description:
  zh: >
      把 Markdown 报告转成中文学位论文风格的 DOCX：中文字体、标题样式、表格阴影、目录与页码。
      
  en: >
      Converts Markdown reports into Chinese thesis-style DOCX: CJK fonts, heading styles, shaded tables, table of contents and page numbers.
      
revision: 285c4b39b3388eefcfbc68832a115017c3159ef2
updated_at: "2026-09-30T13:31:10.829Z"
fingerprint: a1267eaa5ccc3c2e0e14d498c5520c3593d5be87679201f7ccbfe11402a2e6b8
source:
  - path: "research/md_to_docx.py"
apis:
  - protocol: rpc
    path: "md_to_docx.convert"
    description:
      zh: >
          执行转换。
          
      en: >
          Runs the conversion.
          
  - protocol: rpc
    path: "md_to_docx.setup_styles"
    description:
      zh: >
          配置中文字体样式。
          
      en: >
          Configures CJK styles.
          
  - protocol: rpc
    path: "md_to_docx.add_toc"
    description:
      zh: >
          插入目录。
          
      en: >
          Inserts a TOC.
          
---
