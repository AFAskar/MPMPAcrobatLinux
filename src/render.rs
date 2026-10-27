use anyhow::{bail, Result};
use libloading::Library;
use std::ffi::c_void;
type Handle = *mut c_void;
static USERS: std::sync::Mutex<usize> = std::sync::Mutex::new(0);
#[repr(C)]
struct Writer {
    version: i32,
    write: unsafe extern "C" fn(*mut Writer, *const c_void, std::ffi::c_ulong) -> i32,
    bytes: Vec<u8>,
}
unsafe extern "C" fn write_block(
    writer: *mut Writer,
    data: *const c_void,
    size: std::ffi::c_ulong,
) -> i32 {
    // PDFium calls synchronously while Writer and the supplied block are alive.
    unsafe {
        (*writer)
            .bytes
            .extend_from_slice(std::slice::from_raw_parts(data.cast(), size as usize));
    }
    1
}
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
            let mut users = USERS.lock().unwrap();
            if *users == 0 {
                (lib.get::<unsafe extern "C" fn()>(b"FPDF_InitLibrary\0")?)();
            }
            *users += 1;
            Ok(Self {
                lib,
                page_size: std::cell::Cell::new((0., 0.)),
            })
        }
    }
    pub fn print_copy(&self, bytes: &[u8], pages: &[i32]) -> Result<Vec<u8>> {
        unsafe {
            // Resolve all entry points before acquiring native handles so an
            // unavailable symbol cannot leak a document.
            let load = self
                .lib
                .get::<unsafe extern "C" fn(*const u8, usize, *const u8) -> Handle>(
                    b"FPDF_LoadMemDocument64\0",
                )?;
            let create = self
                .lib
                .get::<unsafe extern "C" fn() -> Handle>(b"FPDF_CreateNewDocument\0")?;
            let close = self
                .lib
                .get::<unsafe extern "C" fn(Handle)>(b"FPDF_CloseDocument\0")?;
            let import = self.lib.get::<unsafe extern "C" fn(
                Handle,
                Handle,
                *const i32,
                std::ffi::c_ulong,
                i32,
            ) -> i32>(b"FPDF_ImportPagesByIndex\0")?;
            let load_page = self
                .lib
                .get::<unsafe extern "C" fn(Handle, i32) -> Handle>(b"FPDF_LoadPage\0")?;
            let close_page = self
                .lib
                .get::<unsafe extern "C" fn(Handle)>(b"FPDF_ClosePage\0")?;
            let flatten = self
                .lib
                .get::<unsafe extern "C" fn(Handle, i32) -> i32>(b"FPDFPage_Flatten\0")?;
            let save =
                self.lib
                    .get::<unsafe extern "C" fn(Handle, *mut Writer, std::ffi::c_ulong) -> i32>(
                        b"FPDF_SaveAsCopy\0",
                    )?;
            let source = load(bytes.as_ptr(), bytes.len(), std::ptr::null());
            if source.is_null() {
                bail!("PDFium failed loading print projection")
            }
            let output = create();
            if output.is_null() {
                close(source);
                bail!("PDFium could not create print copy")
            }
            let result = (|| -> Result<Vec<u8>> {
                if import(
                    output,
                    source,
                    pages.as_ptr(),
                    pages.len() as std::ffi::c_ulong,
                    0,
                ) == 0
                {
                    bail!("PDFium failed selecting print pages")
                }
                for index in 0..pages.len() {
                    let page = load_page(output, index as i32);
                    if page.is_null() {
                        bail!("PDFium failed loading print page {index}")
                    }
                    let status = flatten(page, 1); // FLAT_PRINT respects annotation Print and Hidden flags.
                    close_page(page);
                    if status == 0 {
                        bail!("PDFium failed flattening print page {index}")
                    }
                }
                let mut writer = Writer {
                    version: 1,
                    write: write_block,
                    bytes: Vec::new(),
                };
                if save(output, &mut writer, 2) == 0 {
                    bail!("PDFium failed serializing print copy")
                }
                Ok(writer.bytes)
            })();
            close(output);
            close(source);
            result
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
        let mut users = USERS.lock().unwrap();
        *users -= 1;
        if *users != 0 {
            return;
        }
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
