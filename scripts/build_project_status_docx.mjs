import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { deflateRawSync } from "node:zlib";

const target = resolve("TRAJYX_Project_Status_and_ML_Guide.docx");
const xml = (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

function paragraph(text, style = "Normal", options = {}) {
  const props = style ? `<w:pPr><w:pStyle w:val="${style}"/></w:pPr>` : "";
  const bold = options.bold ? "<w:b/>" : "";
  const color = options.color ? `<w:color w:val="${options.color}"/>` : "";
  const font = options.code ? '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>' : "";
  const size = options.code ? '<w:sz w:val="19"/>' : "";
  const runs = String(text).split("\n").map((line, index) =>
    `${index ? "<w:r><w:br/></w:r>" : ""}<w:r><w:rPr>${bold}${color}${font}${size}</w:rPr><w:t xml:space="preserve">${xml(line)}</w:t></w:r>`
  ).join("");
  return `<w:p>${props}${runs}</w:p>`;
}

function table(headers, rows) {
  const allRows = [headers, ...rows];
  const cells = allRows.map((row, rowIndex) => `<w:tr>${row.map((value) => {
    const shade = rowIndex === 0 ? '<w:shd w:fill="173B3B"/>' : "";
    const color = rowIndex === 0 ? "FFFFFF" : "263238";
    return `<w:tc><w:tcPr><w:tcW w:w="2600" w:type="dxa"/>${shade}<w:tcMar><w:top w:w="80" w:type="dxa"/><w:start w:w="110" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/><w:end w:w="110" w:type="dxa"/></w:tcMar></w:tcPr>${paragraph(value, "TableText", { bold: rowIndex === 0, color })}</w:tc>`;
  }).join("")}</w:tr>`).join("");
  return `<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/><w:tblLayout w:type="autofit"/></w:tblPr><w:tblGrid>${headers.map(() => "<w:gridCol w:w=\"2600\"/>").join("")}</w:tblGrid>${cells}</w:tbl>`;
}

const parts = [];
const h1 = (s) => parts.push(paragraph(s, "Heading1"));
const h2 = (s) => parts.push(paragraph(s, "Heading2"));
const p = (s) => parts.push(paragraph(s));
const bullet = (s) => parts.push(paragraph(`•  ${s}`));
const code = (s) => parts.push(paragraph(s, "Code"));
const addTable = (h, r) => parts.push(table(h, r));

parts.push(paragraph("TRAJYX", "Title"));
parts.push(paragraph("Project Status & ML Training Guide", "Subtitle"));
p("तारीख: 2 अक्टूबर 2026  |  Repo: F:\\TRAJYX");
p("यह report बताती है कि अभी क्या काम करता है, क्या अधूरा है, ML model को वास्तविक data पर कैसे train/evaluate करना है, और mobile app शुरू करने से पहले क्या चाहिए।");

h1("एक नज़र में");
addTable(["स्थिति", "अभी का विवरण"], [
  ["Complete", "Phases 0–8, 10–12 और 16; web dashboard में 13 sections"],
  ["Partial", "Phase 9: ML data/training/evaluation tooling तैयार; labelled corpus और evaluated model नहीं"],
  ["Demo", "Phase 17: browser simulation prototype तैयार; API से seed → analyse → alerts → report वाला पूरा walkthrough बाकी"],
  ["Deferred", "Phases 13–15: driver mobile features. निर्देशानुसार अभी mobile app शुरू नहीं किया गया"],
  ["Deployment", "Firebase project, production secrets/configuration, rate limits, audit/security hardening बाकी"],
]);
p("महत्वपूर्ण: simulation में traffic tracks और proximity score पूरी तरह synthetic हैं। उन्हें CCTV measurement या model accuracy न मानें।");

h1("क्या-क्या पूरा है");
addTable(["क्षेत्र", "काम"], [
  ["Foundation और auth", "Monorepo, shared contracts, FastAPI, local/Firebase adapters, roles और verified sign-in"],
  ["Video analysis", "Upload/jobs, YOLO detection, ByteTrack, track paths, safety checks, near-miss/TTC और explainable weighted risk"],
  ["GIS और alerts", "Road segments, risk aggregation/map, nearby risk और server-side driver-alert decision"],
  ["Dashboard", "Overview, monitoring, analysis, cameras, risk map, events, analytics, reports, model health, settings और simulation सहित 13 sections"],
  ["Reports", "Stored report history तथा CSV/JSON export"],
  ["3D replay", "Calibrated track paths time axis पर; near-miss marker; lazy-loaded Three.js; calibration/WebGL न हो तो 2D timeline fallback"],
  ["ML tooling", "Shared feature builder, JSONL dataset assembler, segment+time holdout, XGBoost train/evaluate CLI और artifact loader"],
]);

h1("क्या बाकी है");
addTable(["काम", "क्या चाहिए / अगला कदम"], [
  ["ML model की असली evaluation", "Permission वाला CCTV corpus, human-reviewed ground-truth labels, कई segments/time windows; फिर train/evaluate"],
  ["Production ML serving", "Evaluation के बाद prediction API और model registry integration; फिलहाल heuristic engine ही live score देता है"],
  ["Demo walkthrough", "एक repeatable runbook जो demo data seed करे, sample video analyse करे, zones aggregate करे और alert/report दिखाए"],
  ["Mobile phases 13–15", "अगली मंज़ूरी पर driver home/risk zones, GPS alerts, hazard report और offline queue"],
  ["Production launch", "Firebase project/credentials, rules/indexes deploy, retention policy, rate limiting, audit log और upload scanning"],
  ["Verification/docs", "Python runtime ठीक करके Python/ML checks चलाना, calibrated camera पर 3D browser check और शेष API/data-honesty/CV docs"],
]);

h1("ML model: train और evaluate कैसे होगा");
p("लक्ष्य: किसी road segment और समय-window के लिए independently reviewed 0–100 risk score predict करना। मौजूदा weighted engine का score training target नहीं बनेगा; उससे train करना केवल उसी heuristic की नकल सिखाएगा, accuracy नहीं मापेगा।");
h2("1. Data और labels तैयार करें");
bullet("Camera/CCTV use की अनुमति, recording time, camera calibration और road-segment mapping सुरक्षित रखें। Faces/plates या व्यक्तिगत पहचान training labels में न डालें।");
bullet("हर segment + UTC time window के लिए reviewed target risk score/outcome दें। Label guide बनाएं, कुछ windows दो reviewers से label कराएं, disagreement resolve करें और dataset provenance सुरक्षित रखें।");
bullet("एक immutable dataset version रखें, जैसे junctions-reviewed-v1। Synthetic DEMO records और heuristic-generated target score को evaluation corpus से बाहर रखें।");
bullet("Current splitter को कम-से-कम 5 distinct road segments और split के बाद train/test में 10-10 windows चाहिए। असल उपयोग के लिए इससे काफी अधिक diverse data चाहिए।");
h2("2. Input format");
code('{ "dataset_version":"junctions-reviewed-v1", "segment":{"id":"junction-014","path":[{"latitude":28.61,"longitude":77.20},{"latitude":28.62,"longitude":77.21}],"lanes":3,"speed_limit_kmh":40,"one_way":false}, "window_start":"2026-04-01T08:00:00Z", "window_end":"2026-04-01T09:00:00Z", "events":[], "analyses":[], "target_risk_score":58 }');
p("हर JSON object को एक अलग line पर JSONL file में रखें। `events` और `analyses` TRAJYX record shapes के अनुसार हों। Feature builder event rates, TTC, traffic mix, cyclical time, road geometry और detector coverage बनाता है; missing observations के साथ explicit missing flags रखता है।");
h2("3. Install और commands");
code("python -m pip install -r ml/requirements.txt\npython -m pip install -e shared/python -e ml\n\npython -m trajyx_ml.datasets.build --input datasets/labels/junctions-reviewed-v1.jsonl --dataset-version junctions-reviewed-v1 --output datasets/processed/junctions-reviewed-v1.csv\n\npython -m trajyx_ml.training.train --dataset datasets/processed/junctions-reviewed-v1.csv --output ml/artifacts/trajyx-risk-xgb/1.0.0\n\npython -m trajyx_ml.evaluation.evaluate --dataset datasets/processed/junctions-reviewed-v1.csv --artifact ml/artifacts/trajyx-risk-xgb/1.0.0");
p("Windows PowerShell में इन commands को अलग-अलग चलाएं; हर command अपने line में है। विस्तृत विवरण docs/ml-training.md में है।");
h2("4. Split और metrics");
bullet("Evaluation split पूरा road segment training से अलग रखता है, और test windows को समय में बाद का रखता है। Random row split नहीं होता, इसलिए एक ही junction की लगभग समान windows train और test में leak नहीं होतीं।");
bullet("XGBoost artifact `model.json`; साथ में dataset version, feature list, parameters, row counts और cutoff `metadata.json` में। Evaluation result `evaluation.json` में।");
bullet("Regression metrics: MAE, RMSE, R² (जब परिभाषित हो)। Risk bands के macro precision/recall/F1 और band-wise actual-vs-predicted calibration भी report होंगे।");
bullet("Metrics देखकर segment-wise/time-wise errors और कम sample वाली bands जांचें। कमजोर/unstable model deploy न करें। Model Health में accuracy तभी दिखे जब named dataset पर evaluation रिकॉर्ड हुआ हो।");

h1("इस बदलाव का verification");
bullet("`npm --prefix web run build` सफल: TypeScript और production bundle तैयार हुए। 3D renderer अलग lazy chunk में है। MapLibre vendor bundle 500 KB warning देता है; build fail नहीं हुआ।");
bullet("`git diff --check` सफल। Automated tests इस बदलाव के लिए नहीं चलाए गए।");
bullet("Python compile/train/evaluate चलाने की कोशिश में `.venv` launcher unavailable Windows Store Python path पर गया; इस environment में Python check पूरा नहीं हो सका। इसलिए ML code compile/run status अभी unverified है।");
bullet("341 automated tests और 9/9 full verification का repo record पिछले baseline का है; इसे इस नए code की test result न समझें।");

h1("Mobile शुरू करने से पहले");
p("Mobile app अभी जानबूझकर deferred है। अगला mobile चरण API से nearby risk zones दिखाएगा; फिर device location को alert endpoint से जोड़ेगा; उसके बाद offline hazard reporting और reconnect queue बनेगी। Alert thresholds server पर ही रहेंगे, driver location की retention सीमित होगी।");
p("निर्णय/inputs की जरूरत: Android demo device, API deployment URL, Firebase/Auth choice, location-permission copy, hazard-photo retention और test road/risk zones। Project में Flutter foundation/auth पहले से है; अभी driver risk/alert/report flows बाकी हैं।");

parts.push('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1100" w:right="1050" w:bottom="1050" w:left="1050" w:header="450" w:footer="450" w:gutter="0"/></w:sectPr>');

const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>${parts.join("")}</w:body></w:document>`;
const stylesXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos" w:eastAsia="Nirmala UI"/><w:sz w:val="21"/><w:color w:val="263238"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="130" w:line="280" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="42"/><w:color w:val="176B62"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:rPr><w:sz w:val="28"/><w:color w:val="53706E"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="300" w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="29"/><w:color w:val="176B62"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="220" w:after="80"/></w:pPr><w:rPr><w:b/><w:sz w:val="23"/><w:color w:val="285C59"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="TableText"><w:name w:val="Table Text"/><w:basedOn w:val="Normal"/><w:rPr><w:sz w:val="18"/></w:rPr><w:pPr><w:spacing w:after="40" w:line="240" w:lineRule="auto"/></w:pPr></w:style><w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/><w:pPr><w:shd w:fill="F1F5F4"/><w:spacing w:before="70" w:after="100"/><w:ind w:left="180" w:right="180"/></w:pPr><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="17"/><w:color w:val="263238"/></w:rPr></w:style><w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:color="D7E0DE"/><w:left w:val="single" w:sz="4" w:color="D7E0DE"/><w:bottom w:val="single" w:sz="4" w:color="D7E0DE"/><w:right w:val="single" w:sz="4" w:color="D7E0DE"/><w:insideH w:val="single" w:sz="4" w:color="D7E0DE"/><w:insideV w:val="single" w:sz="4" w:color="D7E0DE"/></w:tblBorders></w:tblPr></w:style></w:styles>`;

const files = [
  ["[Content_Types].xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>`],
  ["_rels/.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>`],
  ["word/document.xml", documentXml],
  ["word/styles.xml", stylesXml],
  ["word/_rels/document.xml.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`],
  ["docProps/core.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>TRAJYX Project Status and ML Training Guide</dc:title><dc:creator>TRAJYX</dc:creator><dc:subject>Project completion status, remaining work, ML workflow</dc:subject><dcterms:created xsi:type="dcterms:W3CDTF">2026-10-02T00:00:00Z</dcterms:created></cp:coreProperties>`],
  ["docProps/app.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>TRAJYX documentation generator</Application></Properties>`],
].map(([name, content]) => [name, Buffer.from(content, "utf8")]);

const crcTable = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k += 1) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
  return c >>> 0;
});
function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

const localParts = [];
const centralParts = [];
let offset = 0;
for (const [name, data] of files) {
  const filename = Buffer.from(name, "utf8");
  const compressed = deflateRawSync(data);
  const crc = crc32(data);
  const local = Buffer.alloc(30 + filename.length);
  local.writeUInt32LE(0x04034b50, 0);
  local.writeUInt16LE(20, 4);
  local.writeUInt16LE(0x0800, 6);
  local.writeUInt16LE(8, 8);
  local.writeUInt16LE(0, 10);
  local.writeUInt16LE(33, 12);
  local.writeUInt32LE(crc, 14);
  local.writeUInt32LE(compressed.length, 18);
  local.writeUInt32LE(data.length, 22);
  local.writeUInt16LE(filename.length, 26);
  filename.copy(local, 30);
  localParts.push(local, compressed);

  const central = Buffer.alloc(46 + filename.length);
  central.writeUInt32LE(0x02014b50, 0);
  central.writeUInt16LE(20, 4);
  central.writeUInt16LE(20, 6);
  central.writeUInt16LE(0x0800, 8);
  central.writeUInt16LE(8, 10);
  central.writeUInt16LE(0, 12);
  central.writeUInt16LE(33, 14);
  central.writeUInt32LE(crc, 16);
  central.writeUInt32LE(compressed.length, 20);
  central.writeUInt32LE(data.length, 24);
  central.writeUInt16LE(filename.length, 28);
  central.writeUInt32LE(offset, 42);
  filename.copy(central, 46);
  centralParts.push(central);
  offset += local.length + compressed.length;
}
const centralDirectory = Buffer.concat(centralParts);
const end = Buffer.alloc(22);
end.writeUInt32LE(0x06054b50, 0);
end.writeUInt16LE(files.length, 8);
end.writeUInt16LE(files.length, 10);
end.writeUInt32LE(centralDirectory.length, 12);
end.writeUInt32LE(offset, 16);
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, Buffer.concat([...localParts, centralDirectory, end]));
process.stdout.write(`Created ${target}\n`);
