using ProofAgent.Coq;
using ProofAgent.Llm;
using ProofAgent.Session;
using ProofAgent.Tools;
using Serilog;
using System.Text;

namespace ProofAgent.Agent;

public class CoqProofRunOrchestrator
{
    #region Fields

    private const string _SsreflectPromptPath = "Agent/CoqProofSsreflect.txt";

    private const string _KnowledgeCollectionPromptPath = "Agent/KnowledgeCollectionPrompt.txt";

    private const string _NoKnowledgeCollectionPromptPath = "Agent/NoKnowledgeCollectionPrompt.txt";
    private const string _EarlySuccessNoProofAssistantText =
        "Proof check passed before proof session. Proof session was skipped.";

    private const string _AllSsreflectText = "all_ssreflect";

    private const string _SsreflectText = "ssreflect";

    private readonly string _InitialUserMessage;

    private readonly CoqKnowledgeCollector _CoqKnowledgeCollector;

    private readonly CoqMultiErrorChecker _MultiErrorChecker;

    private readonly DefinitionDatabase _DefinitionDatabase;

    private readonly LemmaDatabase _LemmaDatabase;

    private readonly ILlmSession _ProofSession;

    private readonly ILogger _Logger;

    private readonly IPromptTextSource _PromptTextSource;

    private readonly ProjectFileSystem _ProjectFileSystem;

    private readonly ICoqSentenceSplitter _SentenceSplitter;

    private readonly LlmChatOptions _LlmChatOptions;

    #endregion Fields

    public CoqProofRunOrchestrator(
        string initialUserMessage,
        CoqKnowledgeCollector coqKnowledgeCollector,
        DefinitionDatabase definitionDatabase,
        LemmaDatabase lemmaDatabase,
        ProjectFileSystem projectFileSystem,
        ICoqSentenceSplitter sentenceSplitter,
        ILlmSession proofSession,
        CoqMultiErrorChecker multiErrorChecker,
        ILogger logger,
        IPromptTextSource promptTextSource,
        LlmChatOptions llmChatOptions)
    {
        if (string.IsNullOrWhiteSpace(initialUserMessage))
        {
            throw new ArgumentException("Initial user message must be non-empty after trim.", nameof(initialUserMessage));
        }

        _InitialUserMessage = initialUserMessage.Trim();
        _CoqKnowledgeCollector = coqKnowledgeCollector
            ?? throw new ArgumentNullException(nameof(coqKnowledgeCollector));
        _DefinitionDatabase = definitionDatabase
            ?? throw new ArgumentNullException(nameof(definitionDatabase));
        _LemmaDatabase = lemmaDatabase ?? throw new ArgumentNullException(nameof(lemmaDatabase));
        _ProjectFileSystem = projectFileSystem
            ?? throw new ArgumentNullException(nameof(projectFileSystem));
        _SentenceSplitter = sentenceSplitter
            ?? throw new ArgumentNullException(nameof(sentenceSplitter));
        _ProofSession = proofSession ?? throw new ArgumentNullException(nameof(proofSession));
        _MultiErrorChecker = multiErrorChecker ?? throw new ArgumentNullException(nameof(multiErrorChecker));
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _PromptTextSource = promptTextSource ?? throw new ArgumentNullException(nameof(promptTextSource));
        _LlmChatOptions = llmChatOptions;
    }

    public async Task<CoqProofRun> RunAsync(CancellationToken cancellationToken)
    {
        _Logger.Information("proof_run start");

        var initialFailures = await _MultiErrorChecker.RunMultiErrorCheckAsync(cancellationToken).ConfigureAwait(false);
        if (initialFailures.Count == 0)
        {
            _Logger.Information("proof_run done: success=true stage=initial_check");
            return new CoqProofRun(true, null, _EarlySuccessNoProofAssistantText, LlmUsage.Zero);
        }

        var useSsreflectUserPrompt = await _InitializeAsync(cancellationToken).ConfigureAwait(false);
        var definitions = _CoqKnowledgeCollector.GetDefinitions(initialFailures);
        
        _Logger.Information("proof_run knowledge_collected: count={Count}", definitions.Count);
        _LogSelectedDefinitions(definitions);
        var formattedKnowledge = _FormatKnowledge(definitions);
        var proof = await _RunProofChatAsync(formattedKnowledge, useSsreflectUserPrompt, cancellationToken).ConfigureAwait(false);
        var totalUsage = proof.TotalUsage;
        if (proof.ExceededMaxToolRounds)
        {
            return _FinishExceededMaxToolRounds("proof", proof.LastAssistantText, totalUsage);
        }

        return await _RunFinalVerificationAsync(proof.LastAssistantText, totalUsage, cancellationToken).ConfigureAwait(false);
    }

    #region Private Methods

    private async Task<bool> _InitializeAsync(CancellationToken cancellationToken)
    {
        var allCoqFiles = _ProjectFileSystem.GetAllCoqFileRelativePaths();
        var useSsreflectUserPrompt = false;
        foreach (var relativePath in allCoqFiles)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var sentences = await _SentenceSplitter
                .SplitAsync(relativePath, cancellationToken)
                .ConfigureAwait(false);
            foreach (var sentence in sentences)
            {
                _DefinitionDatabase.TryAddDefinition(relativePath, sentence);
                _LemmaDatabase.TryAddLemma(relativePath, sentence);
                if (_SentenceEnablesSsreflectPrompt(sentence))
                {
                    useSsreflectUserPrompt = true;
                }
            }
        }

        _Logger.Information(
            "proof_run initialize: coqFileCount={CoqFileCount} ssreflectUserPrompt={SsreflectUserPrompt}",
            allCoqFiles.Count,
            useSsreflectUserPrompt);
        return useSsreflectUserPrompt;
    }

    private static bool _SentenceEnablesSsreflectPrompt(CoqSentence sentence)
    {
        if (sentence.VernacType != CoqSentenceVernacType.Require)
        {
            return false;
        }

        foreach (var token in sentence.Tokens)
        {
            if (string.Equals(token, _SsreflectText, StringComparison.Ordinal)
                || string.Equals(token, _AllSsreflectText, StringComparison.Ordinal))
            {
                return true;
            }
        }

        return false;
    }

    private async Task<LlmChat> _RunProofChatAsync(
        string knowledgeCollectionAssistantText,
        bool useSsreflectUserPrompt,
        CancellationToken cancellationToken)
    {
        _Logger.Information(
            "proof_run proof_chat: enableReasoning={EnableReasoning} reasoningEffort={ReasoningEffort}",
            _LlmChatOptions.EnableReasoning,
            _LlmChatOptions.ReasoningEffort);
        var proofUserMessage = _BuildProofUserMessage(
            _InitialUserMessage,
            knowledgeCollectionAssistantText,
            useSsreflectUserPrompt);
        return await _ProofSession.ChatAsync(proofUserMessage, _LlmChatOptions, cancellationToken).ConfigureAwait(false);
    }

    private async Task<CoqProofRun> _RunFinalVerificationAsync(
        string lastAssistantText,
        LlmUsage totalUsage,
        CancellationToken cancellationToken)
    {
        var failures = await _MultiErrorChecker.RunMultiErrorCheckAsync(cancellationToken).ConfigureAwait(false);
        if (failures.Count == 0)
        {
            _Logger.Information("proof_run done: success=true stage=final_verification");
            return new CoqProofRun(true, null, lastAssistantText, totalUsage);
        }

        var firstCheck = failures[0].Check;
        if (firstCheck.TimedOut)
        {
            _Logger.Warning("proof_run done: success=false stage=final_verification reason=timed_out");
            return new CoqProofRun(false, null, lastAssistantText, totalUsage);
        }

        _Logger.Information(
            "proof_run done: success=false stage=final_verification failureCount={FailureCount}",
            failures.Count);
        return new CoqProofRun(false, firstCheck.Error, lastAssistantText, totalUsage);
    }

    private string _BuildProofUserMessage(
        string initialUserMessage,
        string knowledgeCollectionAssistantText,
        bool useSsreflectUserPrompt)
    {
        var trimmedInitial = initialUserMessage.Trim();
        string message;
        if (string.IsNullOrWhiteSpace(knowledgeCollectionAssistantText))
        {
            var withoutKnowledgeCollection = _PromptTextSource.GetText(_NoKnowledgeCollectionPromptPath);
            message = _ReplacePlaceholder(withoutKnowledgeCollection, "{{InitialUserMessage}}", trimmedInitial).TrimEnd();
        }
        else
        {
            var withKnowledgeCollection = _PromptTextSource.GetText(_KnowledgeCollectionPromptPath);
            var withInitial = _ReplacePlaceholder(withKnowledgeCollection, "{{InitialUserMessage}}", trimmedInitial);
            message = _ReplacePlaceholder(withInitial, "{{KnowledgeCollectionAssistantText}}", knowledgeCollectionAssistantText.Trim())
                .TrimEnd();
        }

        return _AppendSsreflectGuidanceIfNeeded(message, useSsreflectUserPrompt);
    }

    private string _AppendSsreflectGuidanceIfNeeded(string proofUserMessage, bool useSsreflectUserPrompt)
    {
        if (!useSsreflectUserPrompt)
        {
            return proofUserMessage;
        }

        var ssreflectText = _PromptTextSource.GetText(_SsreflectPromptPath).TrimEnd();
        if (ssreflectText.Length == 0)
        {
            return proofUserMessage;
        }

        if (proofUserMessage.Length == 0)
        {
            return ssreflectText;
        }

        return proofUserMessage + "\n\n" + ssreflectText;
    }

    private string _FormatKnowledge(IReadOnlyList<CoqDefinition> definitions)
    {
        if (definitions.Count == 0)
        {
            return string.Empty;
        }

        var builder = new StringBuilder();
        builder.AppendLine("## Definitions helpful for the proof");
        builder.AppendLine();
        for (var i = 0; i < definitions.Count; i++)
        {
            var definition = definitions[i];
            if (i > 0)
            {
                builder.AppendLine();
            }

            builder.AppendLine($"[{i + 1}] {definition.RelativeCoqFilePath}:{definition.StartLineOneBased}-{definition.EndLineOneBased}");
            builder.AppendLine(definition.Text.Trim());
        }

        return builder.ToString().TrimEnd();
    }

    private void _LogSelectedDefinitions(IReadOnlyList<CoqDefinition> definitions)
    {
        foreach (var definition in definitions)
        {
            _Logger.Information(
                "proof_run knowledge_item: {RelativePath}:{StartLine}-{EndLine}",
                definition.RelativeCoqFilePath,
                definition.StartLineOneBased,
                definition.EndLineOneBased);
        }
    }

    private string _ReplacePlaceholder(string text, string placeholder, string value)
    {
        return text.Replace(placeholder, value, StringComparison.Ordinal);
    }

    private CoqProofRun _FinishExceededMaxToolRounds(string stage, string lastAssistantText, LlmUsage totalUsage)
    {
        _Logger.Warning(
            "proof_run done: success=false reason=max_tool_rounds stage={Stage}",
            stage);
        return new CoqProofRun(
            false,
            null,
            lastAssistantText,
            totalUsage,
            ExceededMaxToolRounds: true);
    }

    #endregion Private Methods
}
