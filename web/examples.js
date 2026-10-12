/* 完整的虚构演示简报，不冒充真实商家或验收案例。 */
const StrategyExamples = (() => {
  const common = {priceStatus:"known", purchaseStatus:"known", audienceMode:"known", budgetMode:"amount", currency:"CNY", channelsState:"known", materialsState:"known", teamState:"known", constraintStatus:"known", periodMode:"duration", brandStyle:"清楚直接，不夸大"};
  const templates = [
    {id:"ai", name:"AI 学习产品", note:"演示：从了解功能到试用", values:{...common,
      productName:"知问 AI 学习助手", productCategory:"软件与在线服务", productDescription:"提供错题整理、知识点问答与学习计划功能，支持网页端和移动端使用。",
      productFeatures:"支持按课程整理错题；提供学习计划。依据：演示产品功能清单。", priceInfo:"月订阅39元；可免费试用3天", salesScope:"线上销售", salesRegion:"全国线上", purchaseEntry:"官网产品页有注册试用入口",
      primaryGoal:"推动试用", desiredAction:"开始试用", marketingGoal:"让用户看懂错题整理的用途后进入官网试用", targetAudience:"准备职业资格考试、每天可用学习时间有限的在职人群", marketingProblem:"产品差异讲不清楚", problemDetail:"已有介绍主要罗列功能，尚未说明用户怎样把错题整理用于复习；暂无转化基线。",
      durationDays:"21", budgetRaw:"2000元", budgetAmount:"2000", existingChannels:"品牌微信公众号和官网产品页，团队拥有发布及编辑权限", availableMaterials:"错题整理操作截图、学习计划界面截图；均允许对外展示", teamResources:"运营1人，每周可投入6小时，能写图文和录屏", specialRequirements:"不承诺通过考试；不虚构提分数据；不使用未经许可的用户错题或个人信息"}},
    {id:"tea", name:"奶茶门店", note:"演示：让附近学生知道门店", values:{...common,
      productName:"原味奶茶", productCategory:"食品饮料", productDescription:"提供冷热奶茶，可选择无糖或半糖，支持到店自取。", productFeatures:"可选择无糖或半糖；提供冷热选择。依据：演示门店当前菜单。", priceInfo:"12元/杯，暂无优惠", salesScope:"线下门店", salesRegion:"大学南门外步行约5分钟的商业街", purchaseEntry:"门店现场点单、自取，营业时间11:00—21:00",
      primaryGoal:"建立产品认知", desiredAction:"到店了解或购买", marketingGoal:"先让附近大学生知道位置、价格和点单选择，再引导到店", targetAudience:"附近大学生", marketingProblem:"产品知名度不足", problemDetail:"此前主要靠自然路过，尚未主动传播门店位置；未有到店来源记录。",
      durationDays:"14", budgetRaw:"500元", budgetAmount:"500", existingChannels:"门店微信公众号和门店微信群；店主拥有发布权限，群成员数量未统计", availableMaterials:"真实门头照片、当前菜单照片、两张饮品实拍；可自主使用", teamResources:"店主每周3小时，可制作简单图文；店员可在点单时询问顾客从哪里得知门店", specialRequirements:"不虚构优惠；不宣传健康或减肥效果；不使用抖音、不购买广告；不把糖度选择说成独家优势"}},
    {id:"watch", name:"智能手表", note:"演示：解释功能并承接咨询", values:{...common,
      productName:"跃动智能手表 S2", productCategory:"数码科技", productDescription:"支持心率趋势记录、睡眠时长记录、运动模式记录和手机消息提醒，续航最长7天。", productFeatures:"提供手机消息提醒、运动模式记录。依据：演示产品说明书。最长续航须注明取决于使用条件。", priceInfo:"399元/只，无其他优惠", salesScope:"线上销售", salesRegion:"全国线上", purchaseEntry:"官方店铺产品详情页及店铺客服",
      primaryGoal:"获取咨询线索", desiredAction:"提交咨询", marketingGoal:"帮助用户理解消息提醒与运动记录后，咨询适配信息", targetAudience:"有日常运动记录习惯的城市上班族", marketingProblem:"产品差异讲不清楚", problemDetail:"现有详情页只有参数列表；手机适配型号需客服确认，不能直接声称通用。",
      durationDays:"21", budgetRaw:"1500元", budgetAmount:"1500", existingChannels:"品牌公众号、官方店铺详情页和客服入口，均有编辑权限", availableMaterials:"说明书、真实手表照片、消息提醒演示录屏；允许公开使用", teamResources:"运营1人每周5小时，客服每工作日可处理咨询", specialRequirements:"健康数据不作医疗诊断；不使用医疗效果承诺；未确认前不声称兼容所有手机"}},
    {id:"beauty", name:"护肤产品", note:"演示：说明使用信息", values:{...common,
      productName:"清润保湿精华", productCategory:"美妆个护", productDescription:"含透明质酸钠与泛醇，质地清爽，用于日常保湿；规格30ml。", productFeatures:"包装标注透明质酸钠与泛醇；规格30ml。依据：演示包装成分及规格信息。", priceInfo:"89元/瓶，暂无优惠", salesScope:"线上销售", salesRegion:"全国线上", purchaseEntry:"品牌官方店铺详情页和客服咨询",
      primaryGoal:"建立产品认知", desiredAction:"了解产品信息", marketingGoal:"让消费者看清日常保湿用途和包装信息，再查看详情", targetAudience:"关注日常保湿、偏好清爽肤感的消费者", marketingProblem:"产品差异讲不清楚", problemDetail:"现有介绍只列成分，消费者难理解用途；没有已验证功效或肤质适配数据。",
      durationDays:"14", budgetRaw:"800元", budgetAmount:"800", existingChannels:"品牌微信公众号与官方店铺详情页，可编辑发布", availableMaterials:"真实包装照片、成分标签照片、取用演示；均可公开", teamResources:"运营每周4小时，能制作图文与简单取用演示", specialRequirements:"不宣称治疗、修复疾病、永久改善；不虚构临床数据，不承诺适合所有肤质"}},
    {id:"travel", name:"旅游产品", note:"演示：从路线信息到咨询", values:{...common,
      productName:"周末古镇轻旅行", productCategory:"旅游出行", productDescription:"提供两天一夜小团行程，包含往返交通、住宿和古镇讲解服务，出发地杭州。", productFeatures:"两天一夜行程；包含往返交通、住宿和古镇讲解。依据：演示行程单。", priceStatus:"unknown", priceInfo:"", salesScope:"预约或咨询服务", salesRegion:"杭州出发至古镇", purchaseEntry:"公众号咨询入口，由客服确认日期、价格及剩余名额",
      primaryGoal:"获取咨询线索", desiredAction:"提交咨询", marketingGoal:"让用户看懂两天如何安排及包含项目，再咨询可出发日期", targetAudience:"杭州及周边希望周末短途放松的上班族", marketingProblem:"咨询或线索较少", problemDetail:"已有照片缺少行程解释；尚未确认各日期报价，不能承诺固定价格或名额。",
      durationDays:"14", budgetRaw:"1000元", budgetAmount:"1000", existingChannels:"旅行社微信公众号与咨询客服，均有权限", availableMaterials:"已核对行程单、自摄古镇照片且拥有使用权", teamResources:"运营每周5小时，客服工作日回复咨询", specialRequirements:"不承诺零购物或固定天气；说明包含项目；报价和名额以客服确认结果为准"}},
  ];
  return {templates};
})();
if (typeof module !== "undefined" && module.exports) module.exports = StrategyExamples;
