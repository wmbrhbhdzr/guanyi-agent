# 杀戮尖塔2视觉适配资料

用途：给截图识别提供公开的外形→名称参照与界面显示约定，不是读取游戏内存/存档的通道。
通用识别默认不载入本目录；选“杀戮尖塔2”时附加4张敌人身份和8张增减益参考图，不提供敌人默认血量、伤害或行动表。
模型根据截图外形与参考图比对，未匹配时保留名称null。匹配只是身份候选，仍需核对，不保证绝对准确。

图片来源：[Spire Codex](https://spire-codex.com)，清单`references.json`逐项保存源地址和SHA-256。
身份元数据源自 `https://spire-codex.com/api/monsters?lang=zhs`；图片版权归Mega Crit Games，
本项目仅用少量社区公开参考图辅助课程研究，沿用现有知识库来源说明。
当前收录外骨骼虫、缩小甲虫、熟睡甲虫、虱虫之祖，不代表完整敌人数据库。

增减益原始资料 `data/knowledge_raw/powers.json` 有257项，含图标路径、Buff/Debuff分类及计数类型。
首批8项为难以杀灭、力量、易伤、虚弱、脆弱、敏捷、荆棘、中毒。
名称可依据图标匹配，数值只读当前截图，不因stack_type=Single/Counter而擅自补1或补0。
难以杀灭的可见数值表示单次伤害/生命减少上限，不称作“层数”。状态元数据不代表已触发的对局效果。

`card_rules.json`来源为既有本地原始卡牌数据及 `https://spire-codex.com/api/cards?lang=zhs`。
收录笨拙（CLUMSY）：诅咒、不能被打出、虚无。原始费用-1不是普通能量费用，统一表示为null。
规则字段只在精确识别出卡名后补充，并用rules_source和normalizations标明来源；不把资料当作直接OCR结果。
当前仅支持基础规则，特殊遗物/临时效果使诅咒可打出的情况暂未覆盖。

适配程序位于`guanyi/vision/profiles.py`，与通用模型通信层分开，后续PVZ等游戏应增加独立适配。
