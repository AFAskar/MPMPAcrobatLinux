var iFileName='Generated adventure log mirror.js';
Value('User Script','');
(function(d){
  var r={sentinel:'\u00a0\u2028\ud83d\ude00',errors:[]};
  try {
    r.before={primary:d.getField('Player Name').valueAsString,mirror:d.getField('AdvLog.Player Name').valueAsString};
    r.prefix=DoTemplate('ALlog','Add',null,true);
    var f=d.getField(r.prefix+'AdvLog.Player Name');
    r.after={primary:d.getField('Player Name').valueAsString,mirror:f.valueAsString,page:f.page};
  } catch(e) {r.errors.push({name:e.name,message:String(e)});}
  Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);
