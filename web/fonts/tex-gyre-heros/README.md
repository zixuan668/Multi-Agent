# 工作台拉丁字体：TeX Gyre Heros

工作台英文及数字使用 TeX Gyre Heros 2.004，中文仍使用用户系统的微软雅黑。它是 Helvetica 的近似替代字体，不是 Helvetica。字体由本站提供，不连接字体 CDN，也不安装到操作系统。

## 上游、作者与许可证

- 作者：Bogusław Jackowski、Janusz M. Nowacki；扩展版权 2007–2009，详见上游清单。
- [官方字体说明](https://ctan.org/pkg/tex-gyre-heros)
- [完整、未经修改的上游发行包](https://mirrors.ctan.org/fonts/tex-gyre.zip)
- [本次下载的 CTAN 镜像目录](https://mirrors.ibiblio.org/pub/mirrors/CTAN/fonts/tex-gyre/)
- 字体许可：`GUST-FONT-LICENSE.txt`，结合 `LPPL.txt`；上游清单为 `MANIFEST-TeX-Gyre-Heros.txt`。这些许可证属于字体资产，不改变项目自身代码的许可。

## 本项目的打包记录

2026-10-08：从上述 CTAN 镜像复制 `opentype/texgyreheros-regular.otf` 和 `opentype/texgyreheros-bold.otf`，仅选择工作台实际使用的常规和粗体两个字面。字体文件本身未修改、未重命名、未转换、未裁剪。此目录是项目选取的字体资产集合，不是完整 TeX Gyre 发行包；完整原始发行包可通过上面的链接取得。

CSS 通过 `@font-face` 直接加载原始 OpenType 文件，使用 `font-display: swap`，并限制到拉丁 Unicode 范围，让中文回退到微软雅黑。没有更改字形或字体内部元数据，也不声明上游作者为本项目提供维护或支持。
