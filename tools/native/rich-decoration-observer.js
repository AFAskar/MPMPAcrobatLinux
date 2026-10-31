// Isolated host layout diagnostic: original target actions are deliberately cleared.
var iFileName='Rich decoration geometry matrix.js';
Value('User Script','');
(function(d){
  var f=d.getField('Extra.Notes'),families=[['Segoe UI',400,'normal'],['Segoe UI',700,'normal'],['Segoe UI',400,'italic'],['Segoe UI',700,'italic'],['Arial',400,'normal'],['Times New Roman',400,'normal'],['Calibri',400,'normal'],['Courier New',400,'normal']];
  var cases=[],sizes=[7,10,14],spans=[];
  for(var i=0;i<families.length;i++)for(var j=0;j<sizes.length;j++)cases.push({family:families[i][0],weight:families[i][1],style:families[i][2],size:sizes[j],underline:true,strike:true});
  cases.push({family:'Segoe UI',weight:400,style:'normal',size:7,underline:true,strike:false});
  cases.push({family:'Segoe UI',weight:400,style:'normal',size:7,underline:false,strike:true});
  if(d.__decorationCases)cases=d.__decorationCases;
  ['Keystroke','Validate','Format','Calculate'].forEach(function(kind){f.setAction(kind,'')});
  f.richText=true;f.multiline=true;f.textFont='SegoeUI';f.textSize=7;f.alignment='left';
  for(var k=0;k<cases.length;k++){
    var c=cases[k];c.text='Row'+('0'+k).slice(-2)+' abcXYZpq';
    spans.push({text:c.text+(k+1<cases.length?'\r':''),fontFamily:[c.family],fontWeight:c.weight,fontStyle:c.style,textSize:c.size,textColor:['RGB',0,0,0],linespacing:14,alignment:'left',underline:c.underline,strikethrough:c.strike});
  }
  f.richValue=spans;
  var r={scope:'Isolated action-cleared decoration matrix; not an original MPMB workflow pass',cases:cases,field:{value:f.valueAsString,spans:f.richValue},sentinel:'\u00a0\u2028\ud83d\ude00'};
  Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);
