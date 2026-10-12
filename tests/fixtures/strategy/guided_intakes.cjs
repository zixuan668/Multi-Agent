/* Synthetic user inputs, not real product claims or model quality evidence. */
const brief = require('../../../web/brief.js');
const base = {...brief.defaults, briefVersion:1, priceStatus:'unknown', salesScope:'线上销售', purchaseStatus:'unknown', primaryGoal:'建立产品认知', desiredAction:'咨询产品详情', audienceMode:'known', marketingProblem:'产品差异讲不清楚', budgetMode:'amount', budgetAmount:'1000', currency:'CNY', periodMode:'duration', durationDays:'14', channelsState:'unknown', materialsState:'unknown', teamState:'unknown', constraintStatus:'known', specialRequirements:'不虚构优惠、认证、销量或效果承诺', brandStyle:'清楚直接'};
const products = [
  ['learning','AI学习产品','学习工具','提供错题整理和学习计划功能。','支持按课程归类错题。','学生','了解学习计划如何使用'],
  ['milk-owned','原味奶茶','食品饮料','提供冷热奶茶，支持到店自取。','可选择无糖或半糖。','附近大学生','了解糖度选择并到店点单'],
  ['watch','智能手表','数码产品','支持消息提醒和运动记录。','可查看历史运动记录。','通勤人群','了解消息提醒使用场景'],
  ['cosmetics','自然色号粉底液','美妆产品','提供自然色号和哑光妆效选择。','提供试色卡。','关注妆容的消费者','查看试色信息'],
  ['travel','古城周末游','旅游服务','提供两日行程规划和景点介绍服务。','行程包含古城步行路线。','周末出行游客','咨询路线安排'],
];
const cases = products.map(([case_id,productName,productCategory,productDescription,productFeatures,targetAudience,marketingGoal])=>({case_id,category:productCategory,values:{...base,productName,productCategory,productDescription,productFeatures,targetAudience,marketingGoal}}));
const milk=cases[1];
Object.assign(milk.values,{salesScope:'线下门店',salesRegion:'大学周边',priceStatus:'known',priceInfo:'12 元 / 杯',purchaseStatus:'known',purchaseEntry:'门店现场点单',channelsState:'known',existingChannels:'门店微信群，门店有管理员发布权限',materialsState:'known',availableMaterials:'自有菜单和产品实拍图',teamState:'known',teamResources:'店员每天可投入 30 分钟',desiredAction:'到店了解或购买'});
cases.push({case_id:'milk-unknown',category:milk.category,comparison_group:'milk-resources',values:{...milk.values,channelsState:'unknown',materialsState:'unknown',teamState:'unknown'}});
cases.push({case_id:'milk-zero',category:milk.category,comparison_group:'milk-resources',values:{...milk.values,budgetMode:'zero',channelsState:'none',materialsState:'none',teamState:'known',teamResources:'店主每周可投入 1 小时',specialRequirements:'不虚构优惠或效果；禁止使用抖音；不得付费推广'}});
milk.comparison_group='milk-resources';
cases.push({case_id:'missing-context',category:milk.category,values:{...milk.values,budgetMode:'unknown',periodMode:'unknown',audienceMode:'assist',priceStatus:'unknown',purchaseStatus:'unknown',channelsState:'unknown',materialsState:'unknown',teamState:'unknown'}});
cases.push({case_id:'channel-conflict',category:milk.category,values:{...milk.values,specialRequirements:'必须使用抖音；禁止使用抖音；不虚构优惠或效果'}});
module.exports=cases;
if(require.main===module) process.stdout.write(JSON.stringify(cases.map(({values,...item})=>({...item,requirements:brief.payload(values)}))));
