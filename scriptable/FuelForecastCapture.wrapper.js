// Scriptable source wrapper.
// The maintained implementation lives in FuelForecast/scriptable/.
const _ffm = FileManager.iCloud();
const _ffRoot = _ffm.joinPath(_ffm.documentsDirectory(), "FuelForecast");
const _ffSource = _ffm.joinPath(_ffRoot, "scriptable/FuelForecastCapture.js");

await _ffm.downloadFileFromiCloud(_ffSource);
if (!_ffm.fileExists(_ffSource)) {
  throw new Error("FuelForecast/scriptable/FuelForecastCapture.js fehlt.");
}
await eval(`(async () => {\n${_ffm.readString(_ffSource)}\n})()`);
