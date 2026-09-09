/**
 * ima 知识库/笔记本下拉选项的合并与展示兜底。从 JobFormModal 拆出，逻辑原样搬移。
 */
import type { ImaOption } from "../../services/ima";

export const ROOT_IMA_KNOWLEDGE_FOLDER_OPTION: ImaOption = { label: "根目录", value: "root" };

export const buildDisplayImaKnowledgeFolderOption = (
  folderId?: string | null,
  folderName?: string | null
): ImaOption | null => {
  const normalizedId = (folderId ?? "").trim();
  if (!normalizedId || normalizedId === ROOT_IMA_KNOWLEDGE_FOLDER_OPTION.value) {
    return null;
  }
  const normalizedLabel = (folderName ?? "").trim();
  return {
    value: normalizedId,
    label: normalizedLabel || normalizedId
  };
};

export const mergeImaKnowledgeFolderOptions = (list: ImaOption[], fallbackOption?: ImaOption | null): ImaOption[] => {
  const order: string[] = [];
  const optionMap = new Map<string, ImaOption>();
  const pushOption = (option?: ImaOption | null) => {
    if (!option?.value) {
      return;
    }
    if (!optionMap.has(option.value)) {
      order.push(option.value);
    }
    optionMap.set(option.value, option);
  };
  pushOption(ROOT_IMA_KNOWLEDGE_FOLDER_OPTION);
  pushOption(fallbackOption);
  list.forEach((item) => pushOption(item));
  return order.map((value) => optionMap.get(value)!);
};
