/**
 * ima 账号/笔记本/知识库/文件夹资源的加载与选项派生。
 * 从 JobFormModal 拆出，逻辑原样搬移（watch 与副作用仍留在主组件）。
 */
import { useCallback, useMemo, useState } from "react";
import type { FormInstance } from "antd";
import {
  fetchImaAccounts,
  fetchImaKnowledgeBases,
  fetchImaKnowledgeFolders,
  fetchImaNoteFolders,
  type ImaAccount,
  type ImaOption
} from "../../services/ima";
import {
  ROOT_IMA_KNOWLEDGE_FOLDER_OPTION,
  buildDisplayImaKnowledgeFolderOption,
  mergeImaKnowledgeFolderOptions
} from "./imaOptions";

export type ImaResources = {
  imaAccounts: ImaAccount[];
  imaAccountOptions: { label: string; value: number }[];
  imaNoteFolderOptions: ImaOption[];
  imaKnowledgeBaseOptions: ImaOption[];
  imaKnowledgeFolderOptions: ImaOption[];
  imaLoading: { noteFolders: boolean; knowledgeBases: boolean; knowledgeFolders: boolean };
  defaultImaAccountId: number | undefined;
  loadImaAccounts: () => Promise<void>;
  loadImaNoteFolders: (accountId?: number) => Promise<void>;
  loadImaKnowledgeBases: (accountId?: number) => Promise<void>;
  loadImaKnowledgeFolders: (knowledgeBaseId?: string, accountId?: number) => Promise<void>;
  setImaKnowledgeFolders: React.Dispatch<React.SetStateAction<ImaOption[]>>;
};

export function useImaResources(form: FormInstance): ImaResources {
  const [imaAccounts, setImaAccounts] = useState<ImaAccount[]>([]);
  const [imaNoteFolders, setImaNoteFolders] = useState<ImaOption[]>([]);
  const [imaKnowledgeBases, setImaKnowledgeBases] = useState<ImaOption[]>([]);
  const [imaKnowledgeFolders, setImaKnowledgeFolders] = useState<ImaOption[]>([ROOT_IMA_KNOWLEDGE_FOLDER_OPTION]);
  const [imaLoading, setImaLoading] = useState({
    noteFolders: false,
    knowledgeBases: false,
    knowledgeFolders: false
  });

  const defaultImaAccountId = useMemo(() => imaAccounts.find((item) => item.is_default)?.id, [imaAccounts]);
  const imaAccountOptions = useMemo(
    () =>
      imaAccounts.map((account) => ({
        label: account.name + (account.is_default ? "（默认）" : ""),
        value: account.id
      })),
    [imaAccounts]
  );
  const imaNoteFolderOptions = useMemo(() => imaNoteFolders, [imaNoteFolders]);
  const imaKnowledgeBaseOptions = useMemo(() => imaKnowledgeBases, [imaKnowledgeBases]);
  const imaKnowledgeFolderOptions = useMemo(
    () => (imaKnowledgeFolders.length ? imaKnowledgeFolders : [ROOT_IMA_KNOWLEDGE_FOLDER_OPTION]),
    [imaKnowledgeFolders]
  );

  const loadImaAccounts = useCallback(async () => {
    try {
      const list = await fetchImaAccounts();
      setImaAccounts(list);
    } catch (error) {
      console.error("failed to load ima accounts", error);
    }
  }, []);

  const loadImaNoteFolders = useCallback(async (accountId?: number) => {
    if (!accountId) {
      setImaNoteFolders([]);
      return;
    }
    try {
      setImaLoading((prev) => ({ ...prev, noteFolders: true }));
      const list = await fetchImaNoteFolders(accountId);
      setImaNoteFolders(list);
    } catch (error) {
      console.error("failed to load ima note folders", error);
    } finally {
      setImaLoading((prev) => ({ ...prev, noteFolders: false }));
    }
  }, []);

  const loadImaKnowledgeBases = useCallback(async (accountId?: number) => {
    if (!accountId) {
      setImaKnowledgeBases([]);
      return;
    }
    try {
      setImaLoading((prev) => ({ ...prev, knowledgeBases: true }));
      const list = await fetchImaKnowledgeBases(accountId);
      setImaKnowledgeBases(list);
    } catch (error) {
      console.error("failed to load ima knowledge bases", error);
    } finally {
      setImaLoading((prev) => ({ ...prev, knowledgeBases: false }));
    }
  }, []);

  const loadImaKnowledgeFolders = useCallback(async (knowledgeBaseId?: string, accountId?: number) => {
    if (!knowledgeBaseId || !accountId) {
      setImaKnowledgeFolders((prev) =>
        mergeImaKnowledgeFolderOptions(
          [],
          prev.find((item) => item.value === form.getFieldValue("ima_knowledge_folder_id"))
        )
      );
      return;
    }
    try {
      setImaLoading((prev) => ({ ...prev, knowledgeFolders: true }));
      const list = await fetchImaKnowledgeFolders(knowledgeBaseId, accountId);
      setImaKnowledgeFolders((prev) => {
        const selectedValue = form.getFieldValue("ima_knowledge_folder_id");
        const selectedFallback =
          selectedValue && selectedValue !== ROOT_IMA_KNOWLEDGE_FOLDER_OPTION.value
            ? prev.find((item) => item.value === selectedValue) ??
              buildDisplayImaKnowledgeFolderOption(selectedValue, selectedValue)
            : null;
        return mergeImaKnowledgeFolderOptions(list, selectedFallback);
      });
    } catch (error) {
      console.error("failed to load ima knowledge folders", error);
      setImaKnowledgeFolders((prev) =>
        mergeImaKnowledgeFolderOptions(
          [],
          prev.find((item) => item.value === form.getFieldValue("ima_knowledge_folder_id"))
        )
      );
    } finally {
      setImaLoading((prev) => ({ ...prev, knowledgeFolders: false }));
    }
  }, [form]);

  return useMemo(
    () => ({
      imaAccounts,
      imaAccountOptions,
      imaNoteFolderOptions,
      imaKnowledgeBaseOptions,
      imaKnowledgeFolderOptions,
      imaLoading,
      defaultImaAccountId,
      loadImaAccounts,
      loadImaNoteFolders,
      loadImaKnowledgeBases,
      loadImaKnowledgeFolders,
      setImaKnowledgeFolders
    }),
    [
      imaAccounts,
      imaAccountOptions,
      imaNoteFolderOptions,
      imaKnowledgeBaseOptions,
      imaKnowledgeFolderOptions,
      imaLoading,
      defaultImaAccountId,
      loadImaAccounts,
      loadImaNoteFolders,
      loadImaKnowledgeBases,
      loadImaKnowledgeFolders
    ]
  );
}
