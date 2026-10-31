//! Enter another document realm while a callback already holds the engine guard.
//!
//! Context::with and Context::full acquire that guard themselves and cannot be
//! nested inside a document callback. These helpers use the pinned QuickJS API
//! under the caller's existing guard, with an explicit same-runtime check.
use anyhow::{ensure, Context as _, Result};
use rquickjs::{qjs, Context, Ctx};
use std::ptr::NonNull;

fn runtime(ctx: &Ctx<'_>) -> *mut qjs::JSRuntime {
    // SAFETY: Ctx owns a live context reference throughout this call.
    unsafe { qjs::JS_GetRuntime(ctx.as_raw().as_ptr()) }
}

fn check_owner(parent: &Ctx<'_>, owner: &Context) -> Result<()> {
    // SAFETY: Context owns a live context reference; querying its engine does
    // not enter or acquire a guard on that engine.
    let owned = unsafe { qjs::JS_GetRuntime(owner.as_raw().as_ptr()) };
    ensure!(
        runtime(parent) == owned,
        "Document belongs to another JavaScript runtime"
    );
    Ok(())
}

pub(super) fn create(parent: &Ctx<'_>, owner: &Context) -> Result<Context> {
    check_owner(parent, owner)?;
    // SAFETY: parent proves that this runtime is already guarded on this
    // thread. JS_NewContext creates one owned reference in that same engine.
    let child = NonNull::new(unsafe { qjs::JS_NewContext(runtime(parent)) })
        .context("Unable to allocate source-document JavaScript context")?;
    // SAFETY: child belongs to owner's checked engine and transfers exactly
    // the newly allocated context reference to its normal RAII owner.
    Ok(unsafe { Context::from_raw(child, owner.runtime().clone()) })
}

pub(super) fn enter<'js>(parent: &Ctx<'js>, document: &Context) -> Result<Ctx<'js>> {
    check_owner(parent, document)?;
    // SAFETY: parent holds this same runtime's guard for 'js. from_raw adds
    // its own context reference, so the returned Ctx does not borrow the
    // document owner. It cannot escape the existing guard's invariant lifetime.
    Ok(unsafe { Ctx::from_raw(document.as_raw()) })
}

#[cfg(test)]
mod tests {
    use super::*;
    use rquickjs::{Function, Object, Runtime};
    use std::{
        cell::RefCell,
        rc::{Rc, Weak},
    };

    fn install_opener<'js>(
        ctx: Ctx<'js>,
        owner: Weak<Context>,
        documents: Weak<RefCell<Vec<Context>>>,
    ) -> rquickjs::Result<()> {
        ctx.globals().set(
            "openDocument",
            Function::new(
                ctx.clone(),
                move |ctx: Ctx<'js>| -> rquickjs::Result<Object<'js>> {
                    let owner = owner.upgrade().unwrap();
                    let child = create(&ctx, &owner).unwrap();
                    let child_ctx = enter(&ctx, &child).unwrap();
                    child_ctx.eval::<(), _>("var value=3;function mutate(){return ++value;}")?;
                    documents.upgrade().unwrap().borrow_mut().push(child);
                    Ok(child_ctx.globals())
                },
            )?,
        )
    }

    #[test]
    fn native_document_callback_can_open_and_return_an_independent_live_realm() {
        let engine = Runtime::new().unwrap();
        let owner = Rc::new(Context::full(&engine).unwrap());
        let documents = Rc::new(RefCell::new(Vec::new()));
        owner.with(|ctx| {
            install_opener(ctx.clone(), Rc::downgrade(&owner), Rc::downgrade(&documents)).unwrap();
            assert!(ctx.eval::<bool, _>(
                "var value=9;var source=openDocument();source.mutate()===4 && source.value===4 && value===9"
            ).unwrap());
        });
        assert_eq!(
            documents.borrow()[0].with(|ctx| ctx.eval::<i32, _>("value").unwrap()),
            4
        );
    }

    #[test]
    fn document_objects_and_original_functions_keep_their_own_mutable_realm() {
        let engine = Runtime::new().unwrap();
        let target = Context::full(&engine).unwrap();
        let source = target.with(|ctx| {
            ctx.eval::<(), _>("var name='target'; var value=2; function record(v){value=v;}")
                .unwrap();
            let source = create(&ctx, &target).unwrap();
            let source_ctx = enter(&ctx, &source).unwrap();
            source_ctx
                .globals()
                .set("targetDoc", ctx.globals())
                .unwrap();
            source_ctx
                .eval::<(), _>(
                    "var name='source'; var value=3; var CurrentVars={enabled:false};
                 var selected=['hex'];
                 Array.prototype.find=function(){return 'source prototype'};
                 function Value(v){value=v;targetDoc.record(v+1);}
                 function read(){return name+':'+value+':'+CurrentVars.enabled;}",
                )
                .unwrap();
            ctx.globals()
                .set("sourceDoc", source_ctx.globals())
                .unwrap();
            assert!(ctx
                .eval::<bool, _>(
                    "sourceDoc.CurrentVars.enabled=true;sourceDoc.Value(8);
                 sourceDoc.read()==='source:8:true' && value===9 && name==='target' &&
                 Array.isArray(sourceDoc.selected) && sourceDoc.selected[0]==='hex' &&
                 sourceDoc.selected.find()==='source prototype' &&
                 [1,2].find(function(v){return v===2})===2",
                )
                .unwrap());
            source
        });
        // A later entry observes the same authoritative source state.
        assert_eq!(source.with(|ctx| ctx.eval::<i32, _>("value").unwrap()), 8);
        assert_eq!(target.with(|ctx| ctx.eval::<i32, _>("value").unwrap()), 9);
    }

    #[test]
    fn unrelated_engines_are_rejected_before_entering_or_allocating() {
        let first = Runtime::new().unwrap();
        let second = Runtime::new().unwrap();
        let a = Context::full(&first).unwrap();
        let b = Context::full(&second).unwrap();
        a.with(|ctx| {
            assert!(enter(&ctx, &b).is_err());
            assert!(create(&ctx, &b).is_err());
        });
    }
}
