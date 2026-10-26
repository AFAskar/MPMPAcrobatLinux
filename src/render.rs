use anyhow::{bail, Result};
use libloading::Library;
use std::ffi::c_void;
type Handle = *mut c_void;
// Only rendering is delegated to PDFium. No PDFium form environment/JS isolate is created.
pub struct Renderer {
    lib: Library,
    pub page_size: std::cell::Cell<(f32, f32)>,
}
impl Renderer {
    pub fn new() -> Result<Self> {
        let path =
            std::env::var("MPMB_PDFIUM").unwrap_or_else(|_| "output/deps/lib/libpdfium.so".into());
        unsafe {
            let lib = Library::new(path)?;
            (lib.get::<unsafe extern "C" fn()>(b"FPDF_InitLibrary\0")?)();
            Ok(Self {
                lib,
                page_size: std::cell::Cell::new((0., 0.)),
            })
        }
    }
    pub fn render(&self, bytes: &[u8], page: i32, width: usize) -> Result<(usize, usize, Vec<u8>)> {
        unsafe {
            macro_rules! call { ($name:literal, $ty:ty $(,$a:expr)*) => { (self.lib.get::<$ty>(concat!($name,"\0").as_bytes())?)($($a),*) }; }
            let doc = call!(
                "FPDF_LoadMemDocument64",
                unsafe extern "C" fn(*const u8, usize, *const u8) -> Handle,
                bytes.as_ptr(),
                bytes.len(),
                std::ptr::null()
            );
            if doc.is_null() {
                bail!("PDFium failed loading PDF")
            }
            let mut pg = call!(
                "FPDF_LoadPage",
                unsafe extern "C" fn(Handle, i32) -> Handle,
                doc,
                page
            );
            if pg.is_null() {
                call!("FPDF_CloseDocument", unsafe extern "C" fn(Handle), doc);
                bail!("invalid page {page}")
            }
            // Flatten only this ephemeral render document. The authoritative PDF
            // and all saved outputs retain their interactive widgets and scripts.
            let flat = call!(
                "FPDFPage_Flatten",
                unsafe extern "C" fn(Handle, i32) -> i32,
                pg,
                0
            );
            if flat == 0 {
                call!("FPDF_ClosePage", unsafe extern "C" fn(Handle), pg);
                call!("FPDF_CloseDocument", unsafe extern "C" fn(Handle), doc);
                bail!("PDFium render-only annotation flatten failed")
            }
            if flat == 1 {
                call!("FPDF_ClosePage", unsafe extern "C" fn(Handle), pg);
                pg = call!(
                    "FPDF_LoadPage",
                    unsafe extern "C" fn(Handle, i32) -> Handle,
                    doc,
                    page
                );
                if pg.is_null() {
                    call!("FPDF_CloseDocument", unsafe extern "C" fn(Handle), doc);
                    bail!("reload flattened render page failed")
                }
            }
            let w = call!(
                "FPDF_GetPageWidthF",
                unsafe extern "C" fn(Handle) -> f32,
                pg
            );
            let h = call!(
                "FPDF_GetPageHeightF",
                unsafe extern "C" fn(Handle) -> f32,
                pg
            );
            self.page_size.set((w, h));
            let height = (width as f32 * h / w).ceil() as usize;
            let bm = call!(
                "FPDFBitmap_Create",
                unsafe extern "C" fn(i32, i32, i32) -> Handle,
                width as i32,
                height as i32,
                0
            );
            if bm.is_null() {
                bail!("bitmap allocation failed")
            }
            call!(
                "FPDFBitmap_FillRect",
                unsafe extern "C" fn(Handle, i32, i32, i32, i32, u32) -> i32,
                bm,
                0,
                0,
                width as i32,
                height as i32,
                0xffffffff
            );
            call!(
                "FPDF_RenderPageBitmap",
                unsafe extern "C" fn(Handle, Handle, i32, i32, i32, i32, i32, i32),
                bm,
                pg,
                0,
                0,
                width as i32,
                height as i32,
                0,
                1
            );
            let data = call!(
                "FPDFBitmap_GetBuffer",
                unsafe extern "C" fn(Handle) -> *const u8,
                bm
            );
            let stride = call!(
                "FPDFBitmap_GetStride",
                unsafe extern "C" fn(Handle) -> i32,
                bm
            ) as usize;
            let mut rgba = Vec::with_capacity(width * height * 4);
            for y in 0..height {
                for x in 0..width {
                    let p = std::slice::from_raw_parts(data.add(y * stride + x * 4), 4);
                    rgba.extend_from_slice(&[p[2], p[1], p[0], 255]);
                }
            }
            call!("FPDFBitmap_Destroy", unsafe extern "C" fn(Handle), bm);
            call!("FPDF_ClosePage", unsafe extern "C" fn(Handle), pg);
            call!("FPDF_CloseDocument", unsafe extern "C" fn(Handle), doc);
            Ok((width, height, rgba))
        }
    }
}
impl Drop for Renderer {
    fn drop(&mut self) {
        unsafe {
            if let Ok(f) = self
                .lib
                .get::<unsafe extern "C" fn()>(b"FPDF_DestroyLibrary\0")
            {
                f();
            }
        }
    }
}
