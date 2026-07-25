export type FinalDataType =
  | "string"
  | "int"
  | "float"
  | "datetime"
  | "bool"
  | "unknown";

export interface FillValueOption {
  label: string;
  value: string;
}

type UnknownRecord = Record<string, unknown>;

const asRecord = (value: unknown): UnknownRecord =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {};

const readString = (record: UnknownRecord, key: string): string => {
  const value = record[key];
  return typeof value === "string" ? value : "";
};

export const normalizeDataType = (dtype: unknown): FinalDataType => {
  const normalized =
    typeof dtype === "string" ? dtype.trim().toLowerCase() : "";

  if (
    normalized.includes("datetime") ||
    normalized.includes("timestamp") ||
    normalized === "date"
  ) {
    return "datetime";
  }
  if (normalized.includes("bool")) return "bool";
  if (
    normalized.includes("float") ||
    normalized.includes("double") ||
    normalized.includes("decimal") ||
    normalized === "number" ||
    normalized === "numeric"
  ) {
    return "float";
  }
  if (normalized.includes("int")) return "int";
  if (
    normalized.includes("object") ||
    normalized.includes("string") ||
    normalized === "str" ||
    normalized.includes("category") ||
    normalized.includes("mixed")
  ) {
    return "string";
  }
  return "unknown";
};

export const resolveColumnFinalDataType = (
  payload: unknown,
  columnName: string,
  currentAnswers?: Record<string, string>,
): FinalDataType => {
  const payloadRecord = asRecord(payload);
  const semanticColumns = asRecord(
    asRecord(payloadRecord.semantic_profile).columns,
  );
  const statisticalColumns = asRecord(
    asRecord(payloadRecord.data_profile).columns,
  );
  const semanticDetail = asRecord(semanticColumns[columnName]);
  const statisticalDetail = asRecord(statisticalColumns[columnName]);

  const expectedType = normalizeDataType(
    readString(semanticDetail, "expected_type"),
  );
  const physicalType = normalizeDataType(
    readString(statisticalDetail, "dtype"),
  );

  const castQuestionKey = `Q1_cast_column_${columnName}`;
  const answerKey = `typecast.${castQuestionKey}`;
  const typecastQuestions = asRecord(
    asRecord(payloadRecord.clarifications).typecast,
  );
  const castQuestion = asRecord(typecastQuestions[castQuestionKey]);
  const persistedAnswer =
    readString(castQuestion, "answer") ||
    readString(castQuestion, "previous_answer");
  const castAnswer = (currentAnswers?.[answerKey] || persistedAnswer)
    .trim()
    .toLowerCase();

  if (castAnswer === "yes") {
    return expectedType !== "unknown" ? expectedType : physicalType;
  }
  if (castAnswer === "no") {
    return physicalType !== "unknown" ? physicalType : "string";
  }

  // Until the user opts into casting, the dataset still has its physical dtype.
  return physicalType !== "unknown" ? physicalType : expectedType;
};

export const finalDataTypeToValidationType = (
  dtype: FinalDataType,
): string => {
  if (dtype === "string" || dtype === "unknown") return "str";
  return dtype;
};

export const filterStrategiesForFinalDataType = (
  options: string[],
  finalDataType: FinalDataType,
): string[] =>
  options.filter((option) => {
    const normalized = option
      .replace(/^\(Recommended\)\s*/i, "")
      .trim()
      .toLowerCase();

    if (normalized === "fill_mean") {
      return finalDataType === "int" || finalDataType === "float";
    }
    if (normalized === "fill_median") {
      return (
        finalDataType === "int" ||
        finalDataType === "float" ||
        finalDataType === "datetime"
      );
    }
    return true;
  });

export const getFillValueOptionsForDataType = (
  finalDataType: FinalDataType,
): FillValueOption[] => {
  switch (finalDataType) {
    case "int":
      return [
        { label: "0", value: "0" },
        { label: "-1", value: "-1" },
      ];
    case "float":
      return [
        { label: "-1.0", value: "-1.0" },
        { label: "-999.0", value: "-999.0" },
      ];
    case "datetime":
      return [{ label: "1900-01-01", value: "1900-01-01" }];
    case "bool":
      return [
        { label: "True", value: "True" },
        { label: "False", value: "False" },
      ];
    case "string":
    case "unknown":
    default:
      return [
        { label: "Unknown", value: "Unknown" },
        { label: "N/A", value: "N/A" },
      ];
  }
};

export const getFillValueOptionsForColumn = (
  payload: unknown,
  columnName: string,
  currentAnswers?: Record<string, string>,
): FillValueOption[] => [
  ...getFillValueOptionsForDataType(
    resolveColumnFinalDataType(payload, columnName, currentAnswers),
  ),
  { label: "Custom value (natural language)", value: "custom" },
];
