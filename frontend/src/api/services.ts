import { apiClient } from './client';

export interface UploadResponse {
  run_id: string;
  status: string;
  message: string;
}

export interface RunStatusResponse {
  run_id: string;
  status: string;
  awaiting_hitl: boolean;
  current_checkpoint_id: string | null;
  error_message: string | null;
}

export interface HITLCheckpointResponse {
  checkpoint_id: string;
  checkpoint_type: string;
  message_to_user: string;
  payload: Record<string, any>;
}

export interface HITLDecisionRequest {
  checkpoint_id: string;
  decision: 'approve' | 'reject' | 'modify';
  feedback?: string;
  disambiguation_answers?: Record<string, string | string[]>;
}

const getClarificationEntries = (clarifications: any): any[] => {
  if (!clarifications) return [];
  return ['null', 'duplicate', 'typecast'].flatMap((category) =>
    Object.values(clarifications[category] || {}).filter(Boolean)
  );
};

const hasUnansweredClarifications = (valResult: any): boolean => {
  if (valResult?.status !== 'needs_clarification') return false;
  const questions = getClarificationEntries(valResult.clarifications);
  return questions.some((question: any) => question.answer == null || question.answer === '');
};

const hasAnsweredClarifications = (valResult: any): boolean => {
  const questions = getClarificationEntries(valResult?.clarifications);
  return questions.length > 0 && questions.every((question: any) => question.answer != null && question.answer !== '');
};

export const pipelineApi = {
  uploadFile: async (file: File, requirements: string, cleanFile?: File | null): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_prompt', requirements);
    if (cleanFile) {
      formData.append('clean_file', cleanFile);
    }

    const response = await apiClient.post<any>('/pipeline/run', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    
    return {
      run_id: response.data.run_id,
      status: 'running',
      message: 'Pipeline started successfully',
    };
  },

  uploadBenchmarkFile: async (file: File, cleanFile: File): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('clean_file', cleanFile);

    const response = await apiClient.post<any>('/pipeline/benchmark_run', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    
    return {
      run_id: response.data.run_id,
      status: 'running',
      message: 'Benchmark pipeline started successfully',
    };
  },

  getStatus: async (runId: string): Promise<RunStatusResponse> => {
    const state = await pipelineApi.getFullState(runId);
    return {
      run_id: runId,
      status: state.status,
      awaiting_hitl: state.awaiting_hitl,
      current_checkpoint_id: state.current_checkpoint_id,
      error_message: state.error_message,
    };
  },

  getFullState: async (runId: string): Promise<any> => {
    const response = await apiClient.get<any>(`/pipeline/${runId}/state`);
    const data = response.data;

    // Map LangGraph backend state to frontend UI expectations
    const hasErrors = data.errors && data.errors.length > 0;
    const valResult = data.input_validation_result;
    const isValidationClarification = valResult?.status === 'needs_clarification';
    const nextNodes = Array.isArray(data.next_node)
      ? data.next_node
      : data.next_node
        ? [data.next_node]
        : [];
    const graphAtEnd = nextNodes.length === 0 || nextNodes.includes('__end__');
    const reportCompleted =
      data.current_step === 'reporting' || (data.completed_steps || []).includes('reporting');
    const awaiting_hitl = data.pipeline_mode === 'benchmark'
      ? ((isValidationClarification && valResult?.benchmark_approved !== true) || nextNodes.includes('report_agent'))
      : (hasUnansweredClarifications(valResult) || nextNodes.includes('report_agent'));
    const isResolvingClarification =
      isValidationClarification &&
      hasAnsweredClarifications(valResult) &&
      !data.execution_plan;

    const isCompleted = awaiting_hitl 
      ? false 
      : isResolvingClarification
        ? false
        : graphAtEnd && reportCompleted;
    const isTerminalError = graphAtEnd && hasErrors && !reportCompleted;
      
    const status = isCompleted
      ? 'completed'
      : isTerminalError
        ? 'failed'
        : (awaiting_hitl ? 'awaiting_hitl' : 'running');

    // Dynamic generation of rich logs to visualize the agent workflow
    const agent_logs: any[] = [];
    const agent_thinkings: Record<string, string> = {};

    if (data.agent_logs && typeof data.agent_logs === 'object' && !Array.isArray(data.agent_logs)) {
      for (const [key, val] of Object.entries(data.agent_logs)) {
        if (val && typeof val === 'object') {
          const typedVal = val as any;
          if (Array.isArray(typedVal.logs)) {
            agent_logs.push(...typedVal.logs);
          }
          if (typeof typedVal.thinking === 'string' && typedVal.thinking) {
            agent_thinkings[key] = typedVal.thinking;
          }
        }
      }
      agent_logs.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
    } else if (Array.isArray(data.agent_logs)) {
      agent_logs.push(...data.agent_logs);
    }

    const hasBackendLogs = agent_logs.length > 0;
    if (!hasBackendLogs && data.completed_steps && data.completed_steps.length > 0) {
      if (data.completed_steps.includes('profiling') || data.data_profile) {
        agent_logs.push({
          timestamp: Date.now() / 1000 - 15,
          agent: 'profiler',
          message: `Dataset profiling completed. Analyzed ${data.data_profile?.total_rows || 0} rows and ${data.data_profile?.total_columns || 0} columns.`,
        });
      }
      if (data.completed_steps.includes('input_validation') || data.input_validation_result) {
        agent_logs.push({
          timestamp: Date.now() / 1000 - 5,
          agent: 'input_validator',
          message: `Data quality and user intent validation complete: "${data.input_validation_result?.reasoning || 'No description provided'}"`,
        });
      }
    }

    if (!hasBackendLogs && data.current_step === 'profiling') {
      agent_logs.push({
        timestamp: Date.now() / 1000,
        agent: 'profiler',
        message: 'Running detailed statistical exploratory data analysis (EDA) on uploaded parquet dataset...',
      });
    } else if (!hasBackendLogs && data.current_step === 'input_validation') {
      agent_logs.push({
        timestamp: Date.now() / 1000,
        agent: 'input_validator',
        message: 'Validating dataset quality rules and user prompts using structured LLM validation schema...',
      });
    }

    return {
      run_id: data.run_id,
      status,
      awaiting_hitl,
      resolving_hitl: isResolvingClarification,
      current_checkpoint_id: awaiting_hitl ? runId : null,
      error_message: isTerminalError ? data.errors[0] : null,
      user_requirements: {
        raw_text: data.user_prompt || '',
      },
      structured_cleaning_spec: valResult ? {
        dataset_name: data.original_filename || 'dataset.parquet',
        spec_version: '1.0.0',
        columns_mapping: Object.keys(data.data_profile?.columns || {}).map(col => ({
          original_name: col,
          target_name: col.toLowerCase().replace(/[^a-z0-9_]/g, '_'),
          target_type: data.data_profile?.columns[col]?.dtype || 'string',
          nullable: true,
        })),
        column_rules: Object.keys(data.data_profile?.columns || {}).map(col => ({
          column_name: col,
          strip_whitespace: true,
          case_transformation: 'none',
          imputation: { strategy: 'none' },
        })),
        deduplication: null,
        open_questions: valResult.clarifications ? 
          [
            ...(valResult.clarifications.null ? Object.values(valResult.clarifications.null).map((q: any) => q.question) : []),
            ...(valResult.clarifications.duplicate ? Object.values(valResult.clarifications.duplicate).map((q: any) => q.question) : []),
            ...(valResult.clarifications.typecast ? Object.values(valResult.clarifications.typecast).map((q: any) => q.question) : []),
          ] : [],
        conflicts_detected_by_parser: [],
      } : null,
      requirement_validation: valResult ? {
        is_valid: valResult.status === 'ready',
        blocking: valResult.status === 'needs_clarification',
      } : null,
      agent_logs,
      agent_thinkings,
      next_node: nextNodes,
      current_step: data.current_step,
      completed_steps: data.completed_steps || [],
      task_list: data.task_list || [],
      current_task_idx: data.current_task_idx ?? 0,
      validation_results: data.validation_results || [],
      worker_states: data.worker_states,
      data_profile: data.data_profile,
      semantic_profile: data.semantic_profile,
      input_validation_result: valResult,
      execution_plan: data.execution_plan,
      f1_metrics: data.f1_metrics,
      token_metrics: data.token_metrics ?? {
        total_tokens: 0,
        prompt_tokens: 0,
        completion_tokens: 0,
      },
      pipeline_mode: data.pipeline_mode,
    };
  },


  getCheckpoint: async (runId: string): Promise<HITLCheckpointResponse | null> => {
    const state = await pipelineApi.getFullState(runId);
    const valResult = state.input_validation_result;
    
    const isBenchmarkAwaiting = state.pipeline_mode === 'benchmark' && valResult?.status === 'needs_clarification' && valResult?.benchmark_approved !== true;
    
    if (hasUnansweredClarifications(valResult) || isBenchmarkAwaiting) {
      return {
        checkpoint_id: runId,
        checkpoint_type: 'input_validation_clarification',
        message_to_user: valResult.reasoning || 'Clarifications required.',
        payload: valResult,
      };
    }

    // Second HITL: validation review when interrupted before report_agent
    if (state.next_node && state.next_node.includes('report_agent')) {
      const issues = state.validation_results?.flatMap((item: any) => 
        (item.failed_rules || []).map((rule: string) => ({
          severity: 'error',
          column: item.task_id || 'validation',
          issue_type: 'Validation Failure',
          description: `Rule '${rule}' failed validation on agent '${item.agent}'`,
          affected_rows: item.metrics_observed?.failed_count || 0
        }))
      ) || [];

      const passed = state.validation_results?.every((item: any) => item.passed) ?? true;

      return {
        checkpoint_id: runId + '_review',
        checkpoint_type: 'validation_review',
        message_to_user: 'Please review the execution outcomes and remaining data quality metrics below before accepting the finalized clean dataset.',
        payload: {
          issues,
          validation_result: {
            passed,
            issues
          },
          worker_states: state.worker_states
        }
      };
    }

    return null;
  },

  submitDecision: async (runId: string, data: HITLDecisionRequest): Promise<{ message: string }> => {
    // Call the backend resolve API if we are submitting clarification answers
    if (data.decision === 'approve') {
      if (data.disambiguation_answers) {
        const response = await apiClient.post<{ message: string }>(`/pipeline/${runId}/resolve`, {
          answers: data.disambiguation_answers,
        });
        return response.data;
      } else {
        // Approve final validation results and resume pipeline to report_agent / end
        return pipelineApi.approvePlan(runId);
      }
    }

    return { message: 'Decision submitted successfully' };
  },

  approvePlan: async (
    runId: string,
    payload?: {
      null_review?: {
        strategies: Record<string, {
          strategy: string;
          fill_value: unknown;
          allow_pattern_mismatch: boolean;
          allow_dmv_sentinel: boolean;
        }>;
      };
    },
  ): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>(
      `/pipeline/${runId}/approve_plan`,
      payload,
    );
    return response.data;
  },

  getReport: async (runId: string): Promise<any> => {
    const response = await apiClient.get<any>(`/pipeline/${runId}/report`);
    return response.data;
  },
  
  getProfile: async (runId: string): Promise<any> => {
    const state = await pipelineApi.getFullState(runId);
    if (state.data_profile) {
      state.data_profile.semantic_profile = state.semantic_profile;
    }
    return state.data_profile;
  },

  getProcessedPreview: async (runId: string, limit = 50): Promise<any> => {
    const response = await apiClient.get<any>(`/pipeline/${runId}/preview`, {
      params: { limit },
    });
    return response.data;
  },

  getDatasetComparePreview: async (runId: string, limit = 100, full = false): Promise<any> => {
    const response = await apiClient.get<any>(`/pipeline/${runId}/report/compare-preview`, {
      params: { limit, full },
    });
    return response.data;
  },
  
  getDownloadUrl: (runId: string, format: 'csv' | 'xlsx' | 'parquet' = 'parquet'): string => {
    return `${apiClient.defaults.baseURL}/pipeline/${runId}/download?format=${format}`;
  },

  getReportExportUrl: (runId: string, format: 'json' | 'md' | 'html' = 'md'): string => {
    return `${apiClient.defaults.baseURL}/pipeline/${runId}/report/export?format=${format}`;
  },

  getReportDiagram: async (runId: string, type: 'pipeline' | 'lineage' = 'lineage'): Promise<any> => {
    const response = await apiClient.get<any>(`/pipeline/${runId}/diagram`, {
      params: { type },
    });
    return response.data;
  },

  getTopChangedColumns: async (runId: string, limit = 10): Promise<any> => {
    const response = await apiClient.get<any>(`/pipeline/${runId}/report/changes/top`, {
      params: { limit },
    });
    return response.data;
  },

  getColumnChangeSummary: async (runId: string, columnName: string): Promise<any> => {
    const response = await apiClient.get<any>(`/pipeline/${runId}/report/columns/${encodeURIComponent(columnName)}/changes`);
    return response.data;
  },

  getColumnImpactSummary: async (runId: string, columnName: string): Promise<any> => {
    const response = await apiClient.get<any>(`/pipeline/${runId}/report/columns/${encodeURIComponent(columnName)}/impact`);
    return response.data;
  },

  askReport: async (runId: string, question: string): Promise<any> => {
    const response = await apiClient.post<any>(`/pipeline/${runId}/report/chat`, {
      question,
    });
    return response.data;
  },

  getReportChatHistory: async (runId: string): Promise<any> => {
    const response = await apiClient.get<any>(`/pipeline/${runId}/report/chat`);
    return response.data;
  }
};

