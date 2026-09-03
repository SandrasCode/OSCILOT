# Parking Guidance System Data

## Status Values

The City of Münster's parking guidance system provides, among others, the following values in the `status` field:

| Status | Meaning |
|---|---|
| `frei` | Parking facility is open and occupancy data is available |
| `besetzt` | Parking facility is occupied / full |
| `geschlossen` | Parking facility is closed |
| `keine Angabe` | No occupancy information available |

## Origin of the Abbreviations

The data processing code uses the first three characters of the status value for non-`frei` statuses:

```python
status[:3]

This behavior was identified by inspecting the code responsible for processing the parking guidance system data. As a result, the following abbreviations appear in the processed data:

Original status | Abbreviation
besetzt | bes
geschlossen | ges
keine Angabe | kei

The meaning of the abbreviations were verified by comparing the processed data with the current XML feed of the Münster parking guidance system. The XML feed contains, for example:

Parkplatz Busparkplatz -> keine Angabe
Applying the same three-character abbreviation logic:
"keine Angabe"[:3]  # "kei"
therefore explains in this case the kei values found in the processed data.