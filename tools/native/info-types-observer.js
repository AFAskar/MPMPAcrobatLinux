// Sorted enumeration and typed metadata getters; dates use epochs, not locale text.
var iFileName='Document metadata type observer.js';
Value('User Script','');
(function(d){
  var info=d.info,keys=['Title','Author','Authors','ContactEmail','Subject','Keywords','Creator','Producer','CreationDate','ModDate','Trapped','SheetVersion','SheetVersionType','SheetVersionBuild','SheetType'].concat(d.__infoTypeKeys||[]);
  var r={keys:Object.keys(info).sort(),values:{},errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'};
  for(var i=0;i<keys.length;i++){
    var variants=[keys[i],keys[i].toLowerCase(),keys[i].toUpperCase()];
    for(var j=0;j<variants.length;j++){
      var name=variants[j];
      try {
        var value=info[name],kind=Object.prototype.toString.call(value);
        r.values[name]=kind==='[object Date]'?{type:typeof value,kind:kind,epoch:value.getTime()}:{type:typeof value,kind:kind,text:String(value),array:kind==='[object Array]'?value.slice():null};
      } catch(e) {r.values[name]={getter_error:String(e)};}
    }
  }
  var authors=info.Authors;
  if(Object.prototype.toString.call(authors)==='[object Array]'){
    r.authorsCopy={before:authors.slice()};authors[0]='Diagnostic returned-array change';r.authorsCopy.fresh=info.Authors;r.authorsCopy.local=authors;
  }
  Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);
