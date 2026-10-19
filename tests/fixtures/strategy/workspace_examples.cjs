const brief = require('../../../web/brief.js');
const {templates} = require('../../../web/examples.js');
console.log(JSON.stringify(templates.map(template => ({
  case_id:'example-' + template.id, category:template.name,
  requirements:brief.payload({...brief.defaults,...template.values}),
}))));
