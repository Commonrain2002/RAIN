using ProofAgent.Agent;
using ProofAgent.Cli;
using ProofAgent.Coq;
using ProofAgent.Llm;
using ProofAgent.Session;
using ProofAgent.Tools;
using Serilog;
using Serilog.Events;

public class Program
{
    #region Fields

    private const int MaxToolRounds = 500;

    private const string RunConfigFileName = "proofagent.config.json";

    #endregion Fields

    public static async Task Main(string[] args)
    {
        ILogger logger = _CreateLogger();
        try
        {
            await _RunAsync(args, logger).ConfigureAwait(false);
        }
        finally
        {
            (logger as IDisposable)?.Dispose();
        }
    }

    #region Private Methods

    private static ILogger _CreateLogger()
    {
        var logDir = _GetProofAgentLogDirectory();
        Directory.CreateDirectory(logDir);
        return new LoggerConfiguration()
            .MinimumLevel.Is(LogEventLevel.Information)
            .WriteTo.Console(standardErrorFromLevel: LogEventLevel.Error)
            .WriteTo.File(
                Path.Combine(logDir, "proofagent.log"),
                rollingInterval: RollingInterval.Day,
                shared: true)
            .CreateLogger();
    }

    private static string _GetProofAgentLogDirectory()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "ProofAgent.csproj")))
            {
                return Path.Combine(dir.FullName, "Log");
            }

            dir = dir.Parent;
        }

        return Path.Combine(Directory.GetCurrentDirectory(), "Log");
    }

    private static async Task _RunAsync(string[] args, ILogger logger)
    {
        var runDirectory = Environment.CurrentDirectory;
        var configPath = Path.Combine(runDirectory, RunConfigFileName);
        var resolver = new AgentInputResolver(logger);
        if (!File.Exists(configPath))
        {
            logger.Error(
                "Missing configuration file: {ConfigPath}. Create proofagent.config.json in the current working directory.",
                configPath);
            resolver.PrintMainTaskUsage();
            return;
        }

        var configJson = File.ReadAllText(configPath);
        var llmApiKey = Environment.GetEnvironmentVariable("LLM_API_KEY") ?? "";
        if (!resolver.TryResolveMainTaskInputs(args, configJson, runDirectory, llmApiKey, out var inputs))
        {
            return;
        }

        var projectFileSystem = new ProjectFileSystem(inputs.ProjectRoot);
        var targetCoqFileRelativePath = new RelativePath(inputs.TargetCoqFile, projectFileSystem.Root);
        var processRunner = new ProcessRunner();
        using var cancellationSource = _CreateRunCancellationTokenSource(logger);
        ICoqSentenceSplitter sentenceSplitter = new CoqSentenceSplitterShell(
            projectFileSystem,
            inputs.ParseSentenceScript,
            inputs.CheckTimeoutSeconds,
            logger,
            processRunner);

        IReadOnlyFileSystem promptsRootStore = new ReadOnlyFileSystem(Path.Combine(AppContext.BaseDirectory, "Prompts"));
        var promptTextSource = new FilePromptTextSource(promptsRootStore, logger);
        var toolDeclarations = new ToolDeclarationLoader(promptTextSource);
        var runCheckResultFormatter = new RunCheckToolResultFormatter(promptTextSource);
        var coqProofSkipFinder = new CoqProofSkipFinder(projectFileSystem);
        var coqChecker = new CoqChecker(logger, processRunner, projectFileSystem.Root, coqProofSkipFinder);
        var coqSentenceAnalyzer = new CoqSentenceAnalyzer(logger, sentenceSplitter);
        var coqEnvironmentCapturer = new CoqEnvironmentCapturer(
            projectFileSystem,
            coqChecker,
            coqSentenceAnalyzer,
            inputs.CheckTimeoutSeconds,
            inputs.CheckCommand,
            logger);
        var bulletAnalyzer = new CoqBulletAnalyzer(logger, sentenceSplitter, coqSentenceAnalyzer);
        var bulletIterationPlanner = new CoqProofBulletIterationPlanner(logger, bulletAnalyzer, sentenceSplitter);
        var definitionDatabase = new DefinitionDatabase(logger);
        var lemmaDatabase = new LemmaDatabase(logger);
        var coqKnowledgeCollector = new CoqKnowledgeCollector(definitionDatabase, logger);
        var coqMultiErrorChecker = new CoqMultiErrorChecker(
            logger,
            coqChecker,
            coqEnvironmentCapturer,
            targetCoqFileRelativePath,
            projectFileSystem,
            bulletIterationPlanner,
            inputs.CheckTimeoutSeconds,
            inputs.CheckCommand,
            inputs.ExtraErrorCount);
        var extraReadableRootFileSystems = _CreateExtraReadableRootFileSystems(inputs.ExtraReadableRootPaths);
        var toolExecutionContext = new ToolExecutionContext(
            projectFileSystem,
            extraReadableRootFileSystems,
            inputs.SearchHitContextLines,
            coqMultiErrorChecker,
            runCheckResultFormatter,
            lemmaDatabase);
        var proofTools = new List<ITool>
        {
            new SearchFilesTool(toolDeclarations),
            new ReadLemmaInFileTool(toolDeclarations),
            new ReadFileTool(toolDeclarations),
            new ReplaceBlockInFileTool(toolDeclarations),
            new RunMultiErrorCheckTool(toolDeclarations)
        };
        if (inputs.ExtraReadableRootPaths.Count > 0)
        {
            proofTools.Add(new SearchExtraByRegexTool(toolDeclarations));
            proofTools.Add(new ReadExtraFileTool(toolDeclarations));
        }

        var proofToolRegistry = new ToolRegistry(proofTools);
        var llmHttpTimeout = TimeSpan.FromSeconds(inputs.LlmHttpTimeoutSeconds);
        var llmBaseUri = new Uri(inputs.LlmBaseUrl);
        using var llmHttpClient = new HttpClient();
        var llmProvider = new OpenAICompatibleProvider(
            llmHttpClient,
            inputs.ChatModel,
            llmBaseUri,
            inputs.LlmApiKey,
            logger,
            llmHttpTimeout);
        var enableReasoning = string.Equals(inputs.Thinking, "enabled", StringComparison.Ordinal);
        var llmChatOptions = new LlmChatOptions(enableReasoning, inputs.ReasoningEffort);
        var contextCompressor = new NoOpContextCompressor();
        var runTotalUsage = LlmUsage.Zero;
        // Safe while CoqProofRunOrchestrator calls sessions serially; parallel ChatAsync would need synchronized aggregation.
        Action<LlmSessionUsageReport> onEachHttpResponse = report =>
        {
            runTotalUsage = runTotalUsage.Add(report.ResponseUsage);
            _LogLlmHttpUsage(logger, report, runTotalUsage);
        };

        var proofSystemMessage = promptTextSource.GetText("Agent/CoqProofSystem.txt").TrimEnd();
        var proofSession = new LlmSession(
            llmProvider,
            proofToolRegistry,
            toolExecutionContext,
            contextCompressor,
            proofSystemMessage,
            logger,
            MaxToolRounds,
            onEachHttpResponse);
        var proofRunOrchestrator = new CoqProofRunOrchestrator(
            inputs.InitialUserMessage,
            coqKnowledgeCollector,
            definitionDatabase,
            lemmaDatabase,
            projectFileSystem,
            sentenceSplitter,
            proofSession,
            coqMultiErrorChecker,
            logger,
            promptTextSource,
            llmChatOptions);
        
        CoqProofRun runResult;
        try
        {
            runResult = await proofRunOrchestrator
                .RunAsync(cancellationSource.Token)
                .ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationSource.IsCancellationRequested)
        {
            logger.Information("Run cancelled.");
            return;
        }
        catch (Exception ex)
        {
            logger.Error(ex, "Run failed: {Message}", ex.Message);
            return;
        }

        _LogCoqProofRunResult(logger, runResult, runTotalUsage);
    }

    private static void _LogCoqProofRunResult(
        ILogger logger,
        CoqProofRun runResult,
        LlmUsage runTotalUsage)
    {
        logger.Information(
            "Run cumulative tokens (all HTTP): prompt={PromptTokens} promptCacheHitTokens={PromptCacheHitTokens} promptCacheMissTokens={PromptCacheMissTokens} completion={CompletionTokens} total={TotalTokens}",
            runTotalUsage.PromptTokens,
            runTotalUsage.PromptCacheHitTokens,
            runTotalUsage.PromptCacheMissTokens,
            runTotalUsage.CompletionTokens,
            runTotalUsage.TotalTokens);

        if (runResult.Success)
        {
            logger.Information(
                string.IsNullOrEmpty(runResult.LastAssistantText)
                    ? "(Done: proof check passed; last model turn had no plain text, possibly tool calls only)"
                    : runResult.LastAssistantText);
            return;
        }

        if (runResult.ExceededMaxToolRounds)
        {
            logger.Warning(
                "Agent did not finish within the maximum tool round limit ({MaxToolRounds}). The model kept requesting tools without a final text reply.",
                MaxToolRounds);
            if (!string.IsNullOrWhiteSpace(runResult.LastAssistantText))
            {
                logger.Warning("Last model text output:");
                logger.Warning("{LastAssistantText}", runResult.LastAssistantText);
            }

            return;
        }

        logger.Warning("Proof check did not pass after the proof run final verification. Last error:");
        logger.Warning(
            runResult.LastError == null ? "(unknown error)" : runResult.LastError.ToString());
        if (!string.IsNullOrWhiteSpace(runResult.LastAssistantText))
        {
            logger.Warning("Last model text output:");
            logger.Warning("{LastAssistantText}", runResult.LastAssistantText);
        }
    }

    private static CancellationTokenSource _CreateRunCancellationTokenSource(ILogger logger)
    {
        var cancellationSource = new CancellationTokenSource();
        Console.CancelKeyPress += (_, eventArgs) =>
        {
            eventArgs.Cancel = true;
            if (cancellationSource.IsCancellationRequested)
            {
                return;
            }

            logger.Information("Cancellation requested (Ctrl+C). Stopping after the current operation...");
            cancellationSource.Cancel();
        };

        return cancellationSource;
    }

    private static IReadOnlyList<IReadOnlyFileSystem> _CreateExtraReadableRootFileSystems(IReadOnlyList<string> absolutePaths)
    {
        var stores = new List<IReadOnlyFileSystem>(absolutePaths.Count);
        for (var i = 0; i < absolutePaths.Count; i++)
        {
            stores.Add(new ReadOnlyFileSystem(absolutePaths[i]));
        }

        return stores;
    }

    private static void _LogLlmHttpUsage(ILogger logger, LlmSessionUsageReport report, LlmUsage runCumulative)
    {
        var usage = report.ResponseUsage;
        var sessionCumulative = report.SessionCumulativeUsage;
        logger.Information(
            "LLM usage: enableReasoning={EnableReasoning} reasoningEffort={ReasoningEffort} round={Round}/{MaxRounds}\n" +
            "promptTokens={PromptTokens}\n" +
            "promptCacheHitTokens={PromptCacheHitTokens}\n" +
            "promptCacheMissTokens={PromptCacheMissTokens}\n" +
            "completionTokens={CompletionTokens}\n" +
            "totalTokens={TotalTokens}\n" +
            "sessionCumulativePromptTokens={SessionCumulativePromptTokens}\n" +
            "sessionCumulativePromptCacheHitTokens={SessionCumulativePromptCacheHitTokens}\n" +
            "sessionCumulativePromptCacheMissTokens={SessionCumulativePromptCacheMissTokens}\n" +
            "sessionCumulativeCompletionTokens={SessionCumulativeCompletionTokens}\n" +
            "sessionCumulativeTotalTokens={SessionCumulativeTotalTokens}\n" +
            "runCumulativePromptTokens={RunCumulativePromptTokens}\n" +
            "runCumulativePromptCacheHitTokens={RunCumulativePromptCacheHitTokens}\n" +
            "runCumulativePromptCacheMissTokens={RunCumulativePromptCacheMissTokens}\n" +
            "runCumulativeCompletionTokens={RunCumulativeCompletionTokens}\n" +
            "runCumulativeTotalTokens={RunCumulativeTotalTokens}",
            report.EnableReasoning,
            report.ReasoningEffort,
            report.Round,
            report.MaxToolRounds,
            usage.PromptTokens,
            usage.PromptCacheHitTokens,
            usage.PromptCacheMissTokens,
            usage.CompletionTokens,
            usage.TotalTokens,
            sessionCumulative.PromptTokens,
            sessionCumulative.PromptCacheHitTokens,
            sessionCumulative.PromptCacheMissTokens,
            sessionCumulative.CompletionTokens,
            sessionCumulative.TotalTokens,
            runCumulative.PromptTokens,
            runCumulative.PromptCacheHitTokens,
            runCumulative.PromptCacheMissTokens,
            runCumulative.CompletionTokens,
            runCumulative.TotalTokens);
    }

    #endregion Private Methods
}
