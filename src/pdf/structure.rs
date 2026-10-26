//! Structural projections of the JavaScript-owned page journal.
use super::*;
use std::collections::{BTreeSet, HashMap};

#[derive(Clone, Serialize)]
pub struct Template {
    pub page: ObjectId,
    pub fields: BTreeMap<String, Field>,
    pub order: Vec<String>,
    #[serde(skip_serializing)]
    roots: Vec<ObjectId>,
    #[serde(skip_serializing)]
    owned: BTreeSet<ObjectId>,
}
fn name_entries(d: &Document, node: &Object, out: &mut Vec<(String, ObjectId)>) -> Result<()> {
    let node = resolved(d, node)?.as_dict()?;
    if let Ok(a) = node.get(b"Names").and_then(Object::as_array) {
        for pair in a.chunks_exact(2) {
            out.push((text(d, &pair[0]), pair[1].as_reference()?));
        }
    }
    if let Ok(kids) = node.get(b"Kids").and_then(Object::as_array) {
        for kid in kids {
            name_entries(d, kid, out)?
        }
    }
    Ok(())
}
pub(super) fn templates(
    d: &Document,
    fields: &BTreeMap<String, Field>,
) -> Result<BTreeMap<String, Template>> {
    let mut result = BTreeMap::new();
    let Ok(tree) = d
        .catalog()?
        .get(b"Names")
        .and_then(|v| d.dereference(v).map(|(_, v)| v))
        .and_then(Object::as_dict)
        .and_then(|v| v.get(b"Templates"))
    else {
        return Ok(result);
    };
    let mut entries = Vec::new();
    name_entries(d, tree, &mut entries)?;
    let form = resolved(d, d.catalog()?.get(b"AcroForm")?)?.as_dict()?;
    for (name, page) in entries {
        let pd = d.get_dictionary(page)?;
        let annots = pd
            .get(b"Annots")
            .ok()
            .map(|v| resolved(d, v))
            .transpose()?
            .and_then(|v| v.as_array().ok())
            .cloned()
            .unwrap_or_default();
        let mut owned = BTreeSet::from([page]);
        let mut roots = BTreeSet::new();
        let mut widget_ids = BTreeSet::new();
        for annot in &annots {
            let mut id = annot.as_reference()?;
            owned.insert(id);
            let dict = d.get_dictionary(id)?;
            if dict.get(b"Subtype").and_then(Object::as_name).ok() != Some(b"Widget") {
                continue;
            }
            widget_ids.insert(id);
            let mut visited = BTreeSet::new();
            loop {
                if !visited.insert(id) {
                    bail!("cyclic template field ancestry")
                };
                owned.insert(id);
                let dict = d.get_dictionary(id)?;
                match dict.get(b"Parent").and_then(Object::as_reference) {
                    Ok(parent) => id = parent,
                    Err(_) => {
                        roots.insert(id);
                        break;
                    }
                }
            }
        }
        let mut tf = BTreeMap::new();
        for (n, f) in fields {
            let mut f = f.clone();
            f.widgets.retain(|w| widget_ids.contains(&w.id));
            if f.widgets.is_empty() {
                continue;
            }
            for w in &mut f.widgets {
                w.page = 0;
            }
            tf.insert(n.clone(), f);
        }
        let mut ids = BTreeMap::new();
        for f in tf.values() {
            ids.insert(f.id, f.name.clone());
            for w in &f.widgets {
                ids.insert(w.id, f.name.clone());
            }
        }
        let order = form
            .get(b"CO")
            .and_then(Object::as_array)
            .map(|a| {
                a.iter()
                    .filter_map(|r| r.as_reference().ok().and_then(|id| ids.get(&id).cloned()))
                    .collect()
            })
            .unwrap_or_default();
        result.insert(
            name,
            Template {
                page,
                fields: tf,
                order,
                roots: roots.into_iter().collect(),
                owned,
            },
        );
    }
    Ok(result)
}
fn form_id(d: &Document) -> Result<ObjectId> {
    Ok(d.catalog()?.get(b"AcroForm")?.as_reference()?)
}
fn page_root(d: &Document) -> Result<ObjectId> {
    Ok(d.catalog()?.get(b"Pages")?.as_reference()?)
}
fn array(d: &Document, dict: ObjectId, key: &[u8]) -> Result<Vec<Object>> {
    Ok(d.get_dictionary(dict)?
        .get(key)
        .ok()
        .map(|v| resolved(d, v))
        .transpose()?
        .and_then(|v| v.as_array().ok())
        .cloned()
        .unwrap_or_default())
}
fn inherited_page(d: &Document, id: ObjectId) -> Result<Dictionary> {
    let mut page = d.get_dictionary(id)?.clone();
    let mut next = page.get(b"Parent").and_then(Object::as_reference).ok();
    let mut seen = BTreeSet::new();
    while let Some(id) = next {
        if !seen.insert(id) {
            bail!("cyclic page ancestry")
        };
        let parent = d.get_dictionary(id)?;
        for key in [b"Resources".as_slice(), b"MediaBox", b"CropBox", b"Rotate"] {
            if !page.has(key) {
                if let Ok(v) = parent.get(key) {
                    page.set(key, v.clone());
                }
            }
        }
        next = parent.get(b"Parent").and_then(Object::as_reference).ok();
    }
    Ok(page)
}
fn install_pages(d: &mut Document, pages: &[ObjectId]) -> Result<()> {
    let root = page_root(d)?;
    for id in pages {
        let mut pd = inherited_page(d, *id)?;
        pd.set("Parent", root);
        pd.set("Type", "Page");
        d.objects.insert(*id, Object::Dictionary(pd));
    }
    let root = d.get_dictionary_mut(root)?;
    root.set(
        "Kids",
        pages
            .iter()
            .map(|id| Object::Reference(*id))
            .collect::<Vec<_>>(),
    );
    root.set("Count", pages.len() as i64);
    Ok(())
}
fn prune_fields(d: &mut Document, removed: &BTreeSet<ObjectId>) -> Result<()> {
    // Prune only form ownership edges. Shared actions/resources and named templates remain intact.
    fn prune(
        d: &mut Document,
        r: &Object,
        removed: &BTreeSet<ObjectId>,
        seen: &mut BTreeSet<ObjectId>,
    ) -> Result<bool> {
        let id = r.as_reference()?;
        if removed.contains(&id) {
            return Ok(false);
        }
        if !seen.insert(id) {
            bail!("cyclic form hierarchy")
        }
        let kids = array(d, id, b"Kids")?;
        if kids.is_empty() {
            return Ok(true);
        }
        let mut retained = Vec::new();
        for child in kids {
            if prune(d, &child, removed, seen)? {
                retained.push(child)
            }
        }
        d.get_dictionary_mut(id)?.set("Kids", retained.clone());
        Ok(!retained.is_empty())
    }
    let form = form_id(d)?;
    let mut roots = Vec::new();
    let mut seen = BTreeSet::new();
    for r in array(d, form, b"Fields")? {
        if prune(d, &r, removed, &mut seen)? {
            roots.push(r)
        }
    }
    let co: Vec<_> = array(d, form, b"CO")?
        .into_iter()
        .filter(|r| {
            r.as_reference()
                .map(|id| !removed.contains(&id))
                .unwrap_or(false)
        })
        .collect();
    d.get_dictionary_mut(form)?.set("Fields", roots);
    d.get_dictionary_mut(form)?.set("CO", co);
    Ok(())
}

fn logical_field(d: &mut Document, f: &mut Field) -> Result<ObjectId> {
    let old = f.id;
    let source = d.get_dictionary(old)?.clone();
    if source.get(b"Subtype").and_then(Object::as_name).ok() != Some(b"Widget") {
        return Ok(old);
    }
    let mut parent = source.clone();
    for key in [
        "Type",
        "Subtype",
        "Rect",
        "P",
        "AP",
        "AS",
        "F",
        "BS",
        "MK",
        "H",
        "A",
        "Border",
        "OC",
        "StructParent",
        "NM",
        "M",
        "C",
    ] {
        parent.remove(key.as_bytes());
    }
    parent.set("Kids", vec![Object::Reference(old)]);
    let new = d.add_object(parent);
    let holder = source
        .get(b"Parent")
        .and_then(Object::as_reference)
        .unwrap_or(form_id(d)?);
    let key = if source.has(b"Parent") {
        b"Kids".as_slice()
    } else {
        b"Fields".as_slice()
    };
    let replaced: Vec<_> = array(d, holder, key)?
        .into_iter()
        .map(|r| {
            if r.as_reference().ok() == Some(old) {
                Object::Reference(new)
            } else {
                r
            }
        })
        .collect();
    d.get_dictionary_mut(holder)?.set(key, replaced);
    let original = d.get_dictionary_mut(old)?;
    for key in [
        "FT", "Ff", "T", "TU", "TM", "V", "DV", "DA", "Q", "Opt", "I", "AA",
    ] {
        original.remove(key.as_bytes());
    }
    original.set("Parent", new);
    // Field actions belong to the logical field; the annotation retains its /A action.
    let form = form_id(d)?;
    let co: Vec<_> = array(d, form, b"CO")?
        .into_iter()
        .map(|r| {
            if r.as_reference().ok() == Some(old) {
                Object::Reference(new)
            } else {
                r
            }
        })
        .collect();
    d.get_dictionary_mut(form)?.set("CO", co);
    f.id = new;
    Ok(new)
}
fn shared_spawn(
    d: &mut Document,
    fields: &mut BTreeMap<String, Field>,
    pages: &mut Vec<ObjectId>,
    template: &Template,
    index: usize,
) -> Result<()> {
    let page = d.new_object_id();
    let mut pd = inherited_page(d, template.page)?;
    let old_annots = array(d, template.page, b"Annots")?;
    let mut new_annots = Vec::new();
    for f in fields.values_mut() {
        for w in &mut f.widgets {
            if w.page >= index as i32 {
                w.page += 1
            }
        }
    }
    let owners: BTreeMap<_, _> = template
        .fields
        .iter()
        .flat_map(|(n, f)| f.widgets.iter().map(move |w| (w.id, n.clone())))
        .collect();
    for annot in old_annots {
        let old = annot.as_reference()?;
        let mut widget = d.get_dictionary(old)?.clone();
        let new = d.new_object_id();
        if let Some(name) = owners.get(&old) {
            let f = fields
                .get_mut(name)
                .context("shared template field missing")?;
            let parent = logical_field(d, f)?;
            // The new widget inherits the field value and options, not a duplicated field name.
            for key in [
                "FT", "Ff", "T", "TU", "TM", "V", "DV", "DA", "Q", "Opt", "I", "Kids", "AA",
            ] {
                widget.remove(key.as_bytes());
            }
            widget.set("Parent", parent);
            let mut kids = array(d, parent, b"Kids")?;
            kids.push(new.into());
            d.get_dictionary_mut(parent)?.set("Kids", kids);
            let mut metadata = template.fields[name]
                .widgets
                .iter()
                .find(|w| w.id == old)
                .unwrap()
                .clone();
            metadata.id = new;
            metadata.page = index as i32;
            f.widgets.push(metadata);
        }
        widget.set("P", page);
        d.objects.insert(new, Object::Dictionary(widget));
        new_annots.push(Object::Reference(new));
    }
    pd.set("Type", "Page");
    pd.set("Parent", page_root(d)?);
    pd.set("Annots", new_annots);
    d.objects.insert(page, Object::Dictionary(pd));
    pages.insert(index, page);
    install_pages(d, pages)?;
    Ok(())
}
impl Pdf {
    pub(super) fn structure_projection(
        &self,
        state: &Value,
    ) -> Result<(Document, BTreeMap<String, Field>)> {
        let mut doc = self.doc.clone();
        let mut fields = self.fields.clone();
        let mut pages: Vec<_> = doc.get_pages().into_values().collect();
        for op in state["__structure"].as_array().into_iter().flatten() {
            match op["op"].as_str().unwrap_or("") {
                "spawn" => {
                    let name = op["template"].as_str().context("spawn template name")?;
                    let t = self
                        .templates
                        .get(name)
                        .with_context(|| format!("unknown template {name}"))?;
                    let index = op["index"].as_u64().context("spawn index")? as usize;
                    if index > pages.len() {
                        bail!("spawn page index out of range")
                    }
                    let rename = op["rename"].as_bool().unwrap_or(true);
                    if !rename {
                        shared_spawn(&mut doc, &mut fields, &mut pages, t, index)?;
                        continue;
                    }
                    let mut map = HashMap::new();
                    for id in &t.owned {
                        map.insert(*id, doc.new_object_id());
                    }
                    for id in &t.owned {
                        let mut dict = if *id == t.page {
                            inherited_page(&self.doc, *id)?
                        } else {
                            self.doc.get_dictionary(*id)?.clone()
                        };
                        if let Ok(kids) = dict.get(b"Kids").and_then(Object::as_array) {
                            dict.set(
                                "Kids",
                                kids.iter()
                                    .filter_map(|r| {
                                        r.as_reference()
                                            .ok()
                                            .and_then(|id| map.get(&id))
                                            .map(|id| Object::Reference(*id))
                                    })
                                    .collect::<Vec<_>>(),
                            );
                        }
                        for key in [b"Parent".as_slice(), b"P"] {
                            if let Ok(old) = dict.get(key).and_then(Object::as_reference) {
                                if let Some(new) = map.get(&old) {
                                    dict.set(key, *new);
                                }
                            }
                        }
                        if dict.get(b"Subtype").and_then(Object::as_name).ok() == Some(b"Widget") {
                            dict.set("P", map[&t.page]);
                        }
                        if *id == t.page {
                            dict.set("Type", "Page");
                            dict.set("Parent", page_root(&doc)?);
                            dict.set(
                                "Annots",
                                array(&self.doc, t.page, b"Annots")?
                                    .into_iter()
                                    .map(|r| r.as_reference().map(|id| Object::Reference(map[&id])))
                                    .collect::<std::result::Result<Vec<_>, _>>()?,
                            );
                        }
                        doc.objects.insert(map[id], Object::Dictionary(dict));
                    }
                    let form = form_id(&doc)?;
                    let mut top = array(&doc, form, b"Fields")?;
                    if rename && !t.roots.is_empty() {
                        let parent_name = format!("P{index}");
                        let existing =
                            top.iter().filter_map(|r| r.as_reference().ok()).find(|id| {
                                doc.get_dictionary(*id)
                                    .ok()
                                    .and_then(|d| d.get(b"T").ok())
                                    .map(|v| text(&doc, v))
                                    == Some(parent_name.clone())
                            });
                        let parent=existing.unwrap_or_else(||doc.add_object(dictionary!{"T"=>Object::string_literal(parent_name.as_str()),"Kids"=>Vec::<Object>::new()}));
                        if existing.is_none() {
                            top.push(parent.into())
                        }
                        let cloned_roots: Vec<_> = t
                            .roots
                            .iter()
                            .map(|id| Object::Reference(map[id]))
                            .collect();
                        let group=doc.add_object(dictionary!{"T"=>Object::string_literal(name),"Parent"=>parent,"Kids"=>cloned_roots});
                        let mut kids = array(&doc, parent, b"Kids")?;
                        kids.push(group.into());
                        doc.get_dictionary_mut(parent)?.set("Kids", kids);
                        for root in &t.roots {
                            doc.get_dictionary_mut(map[root])?.set("Parent", group);
                        }
                    }
                    doc.get_dictionary_mut(form)?.set("Fields", top);
                    let mut co = array(&doc, form, b"CO")?;
                    let original_co = array(&self.doc, form_id(&self.doc)?, b"CO")?;
                    let added: Vec<_> = original_co
                        .iter()
                        .filter_map(|r| {
                            r.as_reference()
                                .ok()
                                .and_then(|id| map.get(&id))
                                .copied()
                                .map(Object::Reference)
                        })
                        .collect();
                    co.extend(added);
                    doc.get_dictionary_mut(form)?.set("CO", co);
                    for f in fields.values_mut() {
                        for w in &mut f.widgets {
                            if w.page >= index as i32 {
                                w.page += 1
                            }
                        }
                    }
                    for (n, f) in &t.fields {
                        let mut f = f.clone();
                        f.name = format!("P{index}.{name}.{n}");
                        f.id = map[&f.id];
                        for w in &mut f.widgets {
                            w.id = map[&w.id];
                            w.page = index as i32;
                        }
                        if fields.insert(f.name.clone(), f).is_some() {
                            bail!("duplicate spawned field name")
                        }
                    }
                    pages.insert(index, map[&t.page]);
                    install_pages(&mut doc, &pages)?;
                }
                "deletePages" => {
                    let start = op["start"].as_u64().context("delete start")? as usize;
                    let end = op["end"].as_u64().context("delete end")? as usize;
                    if start > end || end >= pages.len() || end - start + 1 >= pages.len() {
                        bail!("invalid page deletion")
                    }
                    let mut removed = BTreeSet::new();
                    fields.retain(|_, f| {
                        let had_widgets = !f.widgets.is_empty();
                        f.widgets.retain_mut(|w| {
                            if (start as i32..=end as i32).contains(&w.page) {
                                removed.insert(w.id);
                                false
                            } else {
                                if w.page > end as i32 {
                                    w.page -= (end - start + 1) as i32
                                }
                                true
                            }
                        });
                        if had_widgets && f.widgets.is_empty() {
                            removed.insert(f.id);
                            false
                        } else {
                            true
                        }
                    });
                    pages.drain(start..=end);
                    prune_fields(&mut doc, &removed)?;
                    install_pages(&mut doc, &pages)?;
                }
                "removeField" => {
                    let name = op["name"].as_str().context("remove name")?;
                    let mut removed = BTreeSet::new();
                    fields.retain(|n, f| {
                        if n == name || n.starts_with(&format!("{name}.")) {
                            removed.insert(f.id);
                            removed.extend(f.widgets.iter().map(|w| w.id));
                            false
                        } else {
                            true
                        }
                    });
                    for page in &pages {
                        let retained: Vec<_> = array(&doc, *page, b"Annots")?
                            .into_iter()
                            .filter(|r| {
                                r.as_reference()
                                    .map(|id| !removed.contains(&id))
                                    .unwrap_or(false)
                            })
                            .collect();
                        doc.get_dictionary_mut(*page)?.set("Annots", retained);
                    }
                    prune_fields(&mut doc, &removed)?;
                }
                other => bail!("unsupported structural operation {other}"),
            }
        }
        Ok((doc, fields))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> Pdf {
        let mut doc = Document::new();
        let root = doc.new_object_id();
        let form = doc.new_object_id();
        let pages = doc.new_object_id();
        let content = doc.add_object(Stream::new(dictionary! {}, Vec::new()));
        let page=doc.add_object(dictionary!{"Type"=>"Page","Parent"=>pages,"MediaBox"=>vec![0.into(),0.into(),612.into(),792.into()],"Resources"=>dictionary!{},"Contents"=>content});
        let template=doc.add_object(dictionary!{"Type"=>"Template","Parent"=>pages,"MediaBox"=>vec![0.into(),0.into(),612.into(),792.into()],"Resources"=>dictionary!{},"Contents"=>content});
        let base=doc.add_object(dictionary!{"Type"=>"Annot","Subtype"=>"Widget","FT"=>"Tx","T"=>Object::string_literal("A"),"V"=>Object::string_literal("1"),"Rect"=>vec![1.into(),1.into(),20.into(),20.into()],"P"=>page});
        let parent = doc.new_object_id();
        let field=doc.add_object(dictionary!{"Type"=>"Annot","Subtype"=>"Widget","FT"=>"Tx","T"=>Object::string_literal("Str"),"V"=>Object::string_literal("0"),"Rect"=>vec![1.into(),1.into(),20.into(),20.into()],"P"=>template,"Parent"=>parent,"AA"=>dictionary!{"C"=>dictionary!{"S"=>"JavaScript","JS"=>Object::string_literal("event.value=10;")}}});
        doc.set_object(
            parent,
            dictionary! {"T"=>Object::string_literal("Comp"),"Kids"=>vec![field.into()]},
        );
        doc.get_dictionary_mut(page)
            .unwrap()
            .set("Annots", vec![Object::Reference(base)]);
        doc.get_dictionary_mut(template)
            .unwrap()
            .set("Annots", vec![Object::Reference(field)]);
        doc.set_object(
            pages,
            dictionary! {"Type"=>"Pages","Count"=>1,"Kids"=>vec![page.into()]},
        );
        doc.set_object(
            form,
            dictionary! {"Fields"=>vec![base.into(),parent.into()],"CO"=>vec![field.into()]},
        );
        doc.set_object(root,dictionary!{"Type"=>"Catalog","Pages"=>pages,"AcroForm"=>form,"Names"=>dictionary!{"Templates"=>dictionary!{"Names"=>vec![Object::string_literal("AScomp"),template.into()]}}});
        doc.trailer.set("Root", root);
        let mut fields = BTreeMap::new();
        let pm = BTreeMap::from([(base, 0)]);
        for id in [base, parent] {
            walk(&doc, &id.into(), "", &Dictionary::new(), &pm, &mut fields).unwrap();
        }
        let templates = templates(&doc, &fields).unwrap();
        Pdf {
            doc,
            fields,
            templates,
            scripts: vec![],
            order: vec![],
            info: json!({}),
            bookmarks: json!({}),
            path: PathBuf::new(),
        }
    }
    #[test]
    fn spawned_field_ownership_and_calculation_references() {
        let pdf = fixture();
        let original = pdf.templates["AScomp"].fields["Comp.Str"].id;
        let (doc,fields)=pdf.structure_projection(&json!({"__structure":[{"op":"spawn","template":"AScomp","index":1,"rename":true}]})).unwrap();
        let f = &fields["P1.AScomp.Comp.Str"];
        assert_ne!(f.id, original);
        assert_eq!(f.widgets[0].page, 1);
        let page = doc.get_pages()[&2];
        assert_eq!(
            doc.get_dictionary(f.widgets[0].id)
                .unwrap()
                .get(b"P")
                .unwrap()
                .as_reference()
                .unwrap(),
            page
        );
        let co = array(&doc, form_id(&doc).unwrap(), b"CO").unwrap();
        assert!(co.contains(&Object::Reference(f.id)));
        assert_eq!(co.len(), 2);
        assert_eq!(pdf.doc.get_pages().len(), 1);
        assert_eq!(
            text(
                &doc,
                doc.get_dictionary(original).unwrap().get(b"V").unwrap()
            ),
            "0"
        );
    }
    #[test]
    fn deleting_a_spawned_page_prunes_fields_and_updates_surviving_pages() {
        let pdf = fixture();
        let (doc,fields)=pdf.structure_projection(&json!({"__structure":[{"op":"spawn","template":"AScomp","index":1,"rename":true},{"op":"spawn","template":"AScomp","index":2,"rename":true},{"op":"deletePages","start":1,"end":1}]})).unwrap();
        assert!(!fields.contains_key("P1.AScomp.Comp.Str"));
        assert_eq!(fields["P2.AScomp.Comp.Str"].widgets[0].page, 1);
        assert_eq!(doc.get_pages().len(), 2);
        let mut canonical = BTreeMap::new();
        for r in array(&doc, form_id(&doc).unwrap(), b"Fields").unwrap() {
            walk(
                &doc,
                &r,
                "",
                &Dictionary::new(),
                &BTreeMap::new(),
                &mut canonical,
            )
            .unwrap();
        }
        assert!(canonical.contains_key("P2.AScomp.Comp.Str"));
        assert!(!canonical.contains_key("P1.AScomp.Comp.Str"));
        assert_eq!(array(&doc, form_id(&doc).unwrap(), b"CO").unwrap().len(), 2);
    }
    #[test]
    fn shared_template_widgets_retain_one_logical_value_and_survive_deletion() {
        let pdf = fixture();
        let original = pdf.fields["Comp.Str"].id;
        let (doc,fields)=pdf.structure_projection(&json!({"__structure":[{"op":"spawn","template":"AScomp","index":1,"rename":false},{"op":"spawn","template":"AScomp","index":2,"rename":false},{"op":"deletePages","start":1,"end":1}]})).unwrap();
        assert_eq!(fields.len(), pdf.fields.len());
        let f = &fields["Comp.Str"];
        assert_ne!(f.id, original);
        assert_eq!(f.widgets.len(), 2);
        assert_eq!(f.widgets[1].page, 1);
        assert_eq!(array(&doc, f.id, b"Kids").unwrap().len(), 2);
        assert_eq!(
            array(&doc, form_id(&doc).unwrap(), b"CO").unwrap(),
            vec![Object::Reference(f.id)]
        );
        assert_eq!(
            text(&doc, doc.get_dictionary(f.id).unwrap().get(b"V").unwrap()),
            "0"
        );
    }
}
