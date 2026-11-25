//! Live source PDFs used by original cross-document workflows.
use super::{document_context, DocumentServices, Runtime};
use crate::pdf::Pdf;
use anyhow::{bail, Context as _, Result};
use rquickjs::{Context, Ctx, Exception, Function, Object};
use serde_json::{json, Value};
use std::{
    cell::RefCell,
    path::{Path, PathBuf},
    rc::Rc,
    sync::Arc,
};

#[derive(Clone)]
struct Document {
    path: PathBuf,
    context: Context,
    root: bool,
}

pub(super) struct Documents {
    pub(super) services: DocumentServices,
    open: RefCell<Vec<Document>>,
    events: RefCell<Vec<Value>>,
}

impl Documents {
    pub(super) fn new(
        context: Context,
        pdf: Arc<Pdf>,
        services: DocumentServices,
    ) -> Result<Rc<Self>> {
        Ok(Rc::new(Self {
            services,
            open: RefCell::new(vec![Document {
                path: pdf.path.canonicalize()?,
                context,
                root: true,
            }]),
            events: RefCell::new(Vec::new()),
        }))
    }

    pub(super) fn report(&self) -> Value {
        let documents = self.open.borrow().clone();
        let open: Vec<_> = documents
            .iter()
            .map(|doc| {
                let mut item = json!({"path":doc.path,"root":doc.root});
                if !doc.root {
                    // This runs outside the caller's Context::with. Diagnostic
                    // failures stay local and must not change an original action.
                    let observed = doc
                        .context
                        .with(|ctx| Runtime::raw_in(&ctx, "__host.diagnostics()"));
                    item["diagnostics"] =
                        match observed.and_then(|text| Ok(serde_json::from_str::<Value>(&text)?)) {
                            Ok(value) => value,
                            Err(error) => json!({"read_error":format!("{error:#}")}),
                        };
                }
                item
            })
            .collect();
        json!({"open":open,"events":*self.events.borrow()})
    }

    pub(super) fn install<'js>(self: &Rc<Self>, ctx: Ctx<'js>, pdf: &Arc<Pdf>) -> Result<()> {
        let path = pdf.path.canonicalize()?;
        let root = self.open.borrow()[0].context.clone();
        let root_ctx = document_context::enter(&ctx, &root)?;
        for key in ["__nativeApplicationGlobal", "__nativeApplicationState"] {
            let shared = if root_ctx.globals().contains_key(key)? {
                root_ctx.globals().get::<_, Object>(key)?
            } else {
                let shared = Object::new(root_ctx.clone())?;
                root_ctx.globals().set(key, shared.clone())?;
                shared
            };
            ctx.globals().set(key, shared)?;
        }
        let weak = Rc::downgrade(self);
        ctx.globals().set(
            "__openDocument",
            Function::new(
                ctx.clone(),
                move |ctx: Ctx<'js>,
                      path: String,
                      relative: Option<Object<'js>>|
                      -> rquickjs::Result<Object<'js>> {
                    let docs = weak
                        .upgrade()
                        .ok_or_else(|| Exception::throw_message(&ctx, "Document session ended"))?;
                    docs.open_document(&ctx, &path, relative)
                        .map_err(|error| Exception::throw_message(&ctx, &format!("{error:#}")))
                },
            )?,
        )?;
        let weak = Rc::downgrade(self);
        ctx.globals().set(
            "__activeDocuments",
            Function::new(
                ctx.clone(),
                move |ctx: Ctx<'js>| -> rquickjs::Result<Vec<Object<'js>>> {
                    let docs = weak
                        .upgrade()
                        .ok_or_else(|| Exception::throw_message(&ctx, "Document session ended"))?;
                    docs.active(&ctx)
                        .map_err(|error| Exception::throw_message(&ctx, &format!("{error:#}")))
                },
            )?,
        )?;
        let weak = Rc::downgrade(self);
        let close_path = path.clone();
        ctx.globals().set(
            "__closeDocument",
            Function::new(
                ctx.clone(),
                move |ctx: Ctx<'js>, discard: bool| -> rquickjs::Result<bool> {
                    let docs = weak
                        .upgrade()
                        .ok_or_else(|| Exception::throw_message(&ctx, "Document session ended"))?;
                    docs.close_document(&ctx, &close_path, discard)
                        .map_err(|error| Exception::throw_message(&ctx, &format!("{error:#}")))
                },
            )?,
        )?;
        let weak = Rc::downgrade(self);
        ctx.globals().set(
            "__frontDocument",
            Function::new(
                ctx.clone(),
                move |ctx: Ctx<'js>| -> rquickjs::Result<bool> {
                    let docs = weak
                        .upgrade()
                        .ok_or_else(|| Exception::throw_message(&ctx, "Document session ended"))?;
                    docs.front_document(&path)
                        .map_err(|error| Exception::throw_message(&ctx, &format!("{error:#}")))
                },
            )?,
        )?;
        let interactive = self.services.interactive;
        let capabilities = self.services.capabilities;
        ctx.globals().set("__browsePdf", Function::new(ctx.clone(), move |ctx: Ctx<'js>| -> rquickjs::Result<Option<String>> {
            (|| -> Result<Option<String>> {
                if !capabilities.allow_host_fs || !capabilities.allow_native_dialogs {
                    bail!("Native PDF file picker is disabled in server mode");
                }
                if !interactive {bail!("PDF file picker requires interactive mode; scripted imports must supply an explicit path")}
                let chosen = crate::platform::open_file_dialog(
                    "Select MPMB source PDF",
                    "PDF",
                    &["*.pdf"],
                    None,
                    false,
                )?;
                Ok(chosen.map(|p| p.to_string_lossy().into_owned()))
            })().map_err(|error|Exception::throw_message(&ctx,&format!("{error:#}")))
        })?)?;
        Ok(())
    }

    fn active<'js>(&self, ctx: &Ctx<'js>) -> Result<Vec<Object<'js>>> {
        let documents = self.open.borrow().clone();
        documents
            .iter()
            .map(|doc| Ok(document_context::enter(ctx, &doc.context)?.globals()))
            .collect()
    }

    fn resolve<'js>(
        &self,
        ctx: &Ctx<'js>,
        path: &str,
        relative: Option<Object<'js>>,
    ) -> Result<PathBuf> {
        if path.contains("://") {
            bail!("PDF URL opening is unsupported")
        }
        let requested = Path::new(path);
        let resolved = if let Some(relative) = relative {
            let documents = self.open.borrow().clone();
            let mut base = None;
            for doc in documents {
                if document_context::enter(ctx, &doc.context)?.globals() == relative {
                    base = Some(doc.path);
                    break;
                }
            }
            let base =
                base.context("Relative PDF path requires an open document from this session")?;
            base.parent()
                .context("Document has no parent directory")?
                .join(requested)
        } else {
            if !requested.is_absolute() {
                bail!("Relative PDF path requires oDoc")
            }
            requested.to_owned()
        };
        resolved
            .canonicalize()
            .with_context(|| format!("Opening source PDF {}", resolved.display()))
    }

    fn open_document<'js>(
        self: &Rc<Self>,
        ctx: &Ctx<'js>,
        path: &str,
        relative: Option<Object<'js>>,
    ) -> Result<Object<'js>> {
        if !self.services.capabilities.allow_host_fs {
            bail!("Opening host PDF files is disabled in server mode");
        }
        let path = self.resolve(ctx, path, relative)?;
        let existing = self
            .open
            .borrow()
            .iter()
            .find(|doc| doc.path == path)
            .cloned();
        if let Some(existing) = existing {
            return Ok(document_context::enter(ctx, &existing.context)?.globals());
        }
        let pdf = Arc::new(Pdf::open(&path)?);
        let owner = self.open.borrow()[0].context.clone();
        let context = document_context::create(ctx, &owner)?;
        self.open.borrow_mut().push(Document {
            path: path.clone(),
            context: context.clone(),
            root: false,
        });
        let source_ctx = document_context::enter(ctx, &context)?;
        let result = (|| -> Result<()> {
            Runtime::initialize_document(source_ctx.clone(), &pdf, self)?;
            Runtime::eval_in(&source_ctx, "__host.ready()")?;
            Ok(())
        })();
        if let Err(error) = result {
            self.open.borrow_mut().retain(|doc| doc.path != path);
            self.events
                .borrow_mut()
                .push(json!({"operation":"open-failed","path":path,"error":format!("{error:#}")}));
            return Err(error);
        }
        self.events.borrow_mut().push(
            json!({"operation":"open","path":path,"scripts":pdf.scripts.len(),"background":true}),
        );
        Ok(source_ctx.globals())
    }

    fn close_document(&self, ctx: &Ctx<'_>, path: &Path, discard: bool) -> Result<bool> {
        let document = self
            .open
            .borrow()
            .iter()
            .find(|doc| doc.path == path)
            .cloned()
            .context("Document is already closed")?;
        if document.root {
            bail!("Closing the native reader document through JavaScript is not yet supported")
        }
        if !discard {
            bail!("Closing a source PDF requires explicit discard; source save/prompt is not yet supported")
        }
        let source_ctx = document_context::enter(ctx, &document.context)?;
        let diagnostics: Value =
            serde_json::from_str(&Runtime::raw_in(&source_ctx, "__host.diagnostics()")?)?;
        source_ctx.eval::<(), _>("globalThis.__nativeDocumentClosed=true")?;
        self.open.borrow_mut().retain(|doc| doc.path != path);
        self.events
            .borrow_mut()
            .push(json!({"operation":"close-discard","path":path,"diagnostics":diagnostics}));
        Ok(true)
    }

    fn front_document(&self, path: &Path) -> Result<bool> {
        let document = self
            .open
            .borrow()
            .iter()
            .find(|doc| doc.path == path)
            .cloned()
            .context("Document is closed")?;
        if !document.root {
            bail!("Activating a separate source PDF window is not yet supported")
        }
        self.events
            .borrow_mut()
            .push(json!({"operation":"front","path":path}));
        Ok(true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use lopdf::{dictionary, Document as PdfDocument, Object as PdfObject};

    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let directory = std::env::temp_dir().join(format!(
                "mpmb-document-context-{}-{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
            std::fs::create_dir(&directory).unwrap();
            Self(directory)
        }
        fn pdf(&self, name: &str, value: &str) -> PathBuf {
            let mut document = PdfDocument::with_version("1.7");
            let pages = document.new_object_id();
            let field=document.add_object(dictionary!{"Type"=>"Annot","Subtype"=>"Widget","FT"=>"Tx","T"=>PdfObject::string_literal("A"),"V"=>PdfObject::string_literal(value),"DV"=>PdfObject::string_literal("default"),"Rect"=>vec![0.into(),0.into(),100.into(),20.into()],"F"=>4,"DA"=>PdfObject::string_literal("/Helv 8 Tf 0 g")});
            let page=document.add_object(dictionary!{"Type"=>"Page","Parent"=>pages,"MediaBox"=>vec![0.into(),0.into(),200.into(),200.into()],"Annots"=>vec![field.into()]});
            document.objects.insert(
                pages,
                dictionary! {"Type"=>"Pages","Kids"=>vec![page.into()],"Count"=>1}.into(),
            );
            let form = document.add_object(dictionary! {"Fields"=>vec![field.into()]});
            let script=document.add_object(dictionary!{"S"=>"JavaScript","JS"=>PdfObject::string_literal("var tDoc=this;var calls=0;function Value(name,value){calls++;getField(name).value=value;}")});
            let names=document.add_object(dictionary!{"Names"=>vec![PdfObject::string_literal("Original test document code"),script.into()]});
            let catalog=document.add_object(dictionary!{"Type"=>"Catalog","Pages"=>pages,"AcroForm"=>form,"Names"=>dictionary!{"JavaScript"=>names}});
            document.trailer.set("Root", catalog);
            let path = self.0.join(name);
            document.save(&path).unwrap();
            std::fs::canonicalize(&path).unwrap_or(path)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn caught_scripted_dialog_failures_remain_probe_failures() {
        let files = Fixture::new();
        let path = files.pdf("dialog-controls.pdf", "target");
        let replies = vec![
            json!({"title":"Wrong dialog","result":"ok"}),
            json!({"header":"Wrong header","result":"ok"}),
            json!({"button_path":["Missing"]}),
            json!({"select":{"list":"Missing"},"result":"ok"}),
            json!({"title":"Actual dialog","result":"ok"}),
        ];
        let runtime = Runtime::new(
            &Arc::new(Pdf::open(&path).unwrap()),
            replies,
            vec![],
            false,
            None,
            None,
        )
        .unwrap();
        runtime.eval("var caught=0,committed=0;function ask(){return app.execDialog({description:{name:'Actual dialog',elements:[{type:'static_text',item_id:'head',name:'Actual header'},{type:'list_box',item_id:'list'},{type:'ok_cancel'}]},initialize:function(d){d.load({list:{Offered:-1}})},commit:function(){committed++}})}").unwrap();
        for expected in 1..=4 {
            assert_eq!(
                runtime.eval("try{ask()}catch(e){caught++}caught").unwrap(),
                json!(expected)
            );
            let errors = runtime.diagnostics().unwrap()["errors"]
                .as_array()
                .unwrap()
                .clone();
            assert_eq!(errors.len(), expected);
            assert!(errors.iter().all(|e| e["kind"] == "dialog_control"
                && e["source_document"] == path.to_string_lossy().as_ref()));
        }
        // A valid offered reply still runs commit, but cannot erase earlier
        // failures. Repeated diagnostic reads must not duplicate records.
        assert_eq!(runtime.eval("ask();committed").unwrap(), json!(1));
        assert_eq!(
            runtime.diagnostics().unwrap()["errors"]
                .as_array()
                .unwrap()
                .len(),
            4
        );
        assert_eq!(
            runtime.diagnostics().unwrap()["errors"]
                .as_array()
                .unwrap()
                .len(),
            4
        );
        assert_eq!(
            runtime.eval("try{ask()}catch(e){caught++}caught").unwrap(),
            json!(5)
        );
        let errors = runtime.diagnostics().unwrap();
        assert_eq!(errors["errors"].as_array().unwrap().len(), 5);
        assert!(errors["errors"][4]["error"]
            .as_str()
            .unwrap()
            .starts_with("Unanswered dialog:"));
    }

    #[test]
    fn valid_scripted_dialog_has_clean_control_diagnostics() {
        let files = Fixture::new();
        let path = files.pdf("valid-dialog.pdf", "target");
        let runtime = Runtime::new(
            &Arc::new(Pdf::open(&path).unwrap()),
            vec![json!({"title":"Actual dialog","result":"ok"})],
            vec![],
            false,
            None,
            None,
        )
        .unwrap();
        assert_eq!(runtime.eval("var committed=0;app.execDialog({description:{name:'Actual dialog',elements:[{type:'ok_cancel'}]},commit:function(){committed++}});committed").unwrap(), json!(1));
        assert_eq!(runtime.diagnostics().unwrap()["errors"], json!([]));
    }

    #[test]
    fn caught_alert_control_failures_cannot_be_hidden_by_original_code() {
        let files = Fixture::new();
        let path = files.pdf("alert-controls.pdf", "target");
        let runtime = Runtime::new(
            &Arc::new(Pdf::open(&path).unwrap()),
            vec![],
            vec![
                json!(1),
                json!({"title":"Wrong confirmation","button":4}),
                json!(4),
            ],
            false,
            None,
            None,
        )
        .unwrap();
        runtime.eval("var caught=0;function confirm(){if(app.alert({cTitle:'Actual confirmation',cMsg:'Continue?',nType:2})===4)Value('A','confirmed')}").unwrap();
        for expected in 1..=2 {
            assert_eq!(
                runtime
                    .eval("try{confirm()}catch(e){caught++}caught")
                    .unwrap(),
                json!(expected)
            );
            assert_eq!(runtime.snapshot().unwrap()["A"]["value"], json!("target"));
            let errors = runtime.diagnostics().unwrap();
            let errors = errors["errors"].as_array().unwrap();
            assert_eq!(errors.len(), expected);
            assert!(errors.iter().all(|e| e["kind"] == "alert_control"
                && e["source_document"] == path.to_string_lossy().as_ref()));
        }
        runtime.eval("confirm()").unwrap();
        assert_eq!(
            runtime.snapshot().unwrap()["A"]["value"],
            json!("confirmed")
        );
        assert_eq!(
            runtime.diagnostics().unwrap()["errors"]
                .as_array()
                .unwrap()
                .len(),
            2
        );
        // No reply is not an offered user decision, even if the sheet catches it.
        assert_eq!(
            runtime
                .eval("try{confirm()}catch(e){caught++}caught")
                .unwrap(),
            json!(3)
        );
        let errors = runtime.diagnostics().unwrap();
        assert_eq!(errors["errors"].as_array().unwrap().len(), 3);
        assert!(errors["errors"][2]["error"]
            .as_str()
            .unwrap()
            .starts_with("Unanswered alert:"));
        assert_eq!(runtime.diagnostics().unwrap()["errors"], errors["errors"]);
    }

    #[test]
    fn valid_no_and_yes_alerts_keep_clean_control_diagnostics() {
        let files = Fixture::new();
        let path = files.pdf("valid-alerts.pdf", "target");
        let runtime = Runtime::new(
            &Arc::new(Pdf::open(&path).unwrap()),
            vec![],
            vec![
                json!(3),
                json!({"title":"Actual confirmation","button":4,"checked":true}),
            ],
            false,
            None,
            None,
        )
        .unwrap();
        runtime.eval("var box={cMsg:'Remember',bInitialValue:false};function confirm(){if(app.alert({cTitle:'Actual confirmation',cMsg:'Continue?',nType:2,oCheckbox:box})===4)Value('A','confirmed')};confirm()").unwrap();
        assert_eq!(runtime.snapshot().unwrap()["A"]["value"], json!("target"));
        runtime.eval("confirm()").unwrap();
        assert_eq!(
            runtime.snapshot().unwrap()["A"]["value"],
            json!("confirmed")
        );
        assert_eq!(runtime.eval("box.bAfterValue").unwrap(), json!(true));
        assert_eq!(runtime.diagnostics().unwrap()["errors"], json!([]));
    }

    #[test]
    fn source_documents_reuse_live_state_and_discard_without_writing_inputs() {
        let files = Fixture::new();
        let target = files.pdf("target.pdf", "target");
        let source = files.pdf("source.pdf", "source");
        let before = std::fs::read(&source).unwrap();
        let runtime = Runtime::new(
            &Arc::new(Pdf::open(&target).unwrap()),
            vec![],
            vec![],
            false,
            None,
            None,
        )
        .unwrap();
        let observed=runtime.eval("var source=app.openDoc({cPath:'source.pdf',oDoc:this,bHidden:true});source.Value('A','changed');var same=app.openDoc({cPath:'source.pdf',oDoc:this,bHidden:true});var result={same:same===source,source:source.getField('A').valueAsString,target:getField('A').valueAsString,calls:source.calls,sharedGlobal:source.global===global,count:app.activeDocs.length};source.app.calculate=false;result.sharedCalculate=app.calculate===false;app.calculate=true;source.closeDoc(true);result.closedCount=app.activeDocs.length;try{source.getField('A');result.closedGetterRejected=false}catch(e){result.closedGetterRejected=true}var reopened=app.openDoc({cPath:'source.pdf',oDoc:this,bHidden:true});result.reopened=reopened.getField('A').valueAsString;result.reopenedCalls=reopened.calls;reopened.closeDoc(true);result").unwrap();
        assert_eq!(
            observed,
            json!({"same":true,"source":"changed","target":"target","calls":1,"sharedGlobal":true,"count":2,"sharedCalculate":true,"closedCount":1,"closedGetterRejected":true,"reopened":"source","reopenedCalls":0})
        );
        assert_eq!(std::fs::read(source).unwrap(), before);
    }

    #[test]
    fn console_is_application_scoped_and_survives_source_discard_without_dirtying_fields() {
        let files = Fixture::new();
        let target = files.pdf("target.pdf", "target");
        files.pdf("source.pdf", "source");
        let runtime = Runtime::new(
            &Arc::new(Pdf::open(&target).unwrap()),
            vec![],
            vec![],
            false,
            None,
            None,
        )
        .unwrap();
        let observed = runtime.eval(r#"var printed=console.println('root output');console.show();var source=app.openDoc({cPath:'source.pdf',oDoc:this,bHidden:true});source.console.println('\u00a0\u2028\ud83d\ude00');source.closeDoc(true);var view=__host.consoleView(),out={printlnReturn:printed,visible:view.visible,messages:view.messages.slice(),root:getField('A').valueAsString,dirty:dirty};view.messages.length=0;out.snapshotIsCopy=__host.consoleView().messages.length===2;console.clear();out.clearLeavesVisible=__host.consoleView().visible;out.cleared=__host.consoleView().messages.length;__host.consoleVisible(false);out.closed=__host.consoleView().visible;out.diagnosticErrors=JSON.parse(__host.diagnostics()).errors.length;out"#).unwrap();
        assert_eq!(
            observed,
            json!({"printlnReturn":true,"visible":true,"messages":[{"document":"target.pdf","text":"root output"},{"document":"source.pdf","text":"\u{a0}\u{2028}😀"}],"root":"target","dirty":false,"snapshotIsCopy":true,"clearLeavesVisible":true,"cleared":0,"closed":false,"diagnosticErrors":0})
        );
    }

    #[test]
    fn invalid_relative_owners_and_missing_files_leave_the_target_intact() {
        let files = Fixture::new();
        let target = files.pdf("target.pdf", "target");
        let runtime = Runtime::new(
            &Arc::new(Pdf::open(&target).unwrap()),
            vec![],
            vec![],
            false,
            None,
            None,
        )
        .unwrap();
        assert_eq!(runtime.eval("var failures=0;for(var request of [{cPath:'missing.pdf',oDoc:this},{cPath:'target.pdf',oDoc:{}},{cPath:'https://example.invalid/test.pdf'},{cPath:'target.pdf'}]){try{app.openDoc(request)}catch(e){failures++}}({failures:failures,count:app.activeDocs.length,value:getField('A').valueAsString,calculate:app.calculate})").unwrap(),json!({"failures":4,"count":1,"value":"target","calculate":true}));
    }
}
