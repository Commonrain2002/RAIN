using Serilog;

namespace ProofAgent.Cli;

public class AgentInputResolver
{
    #region Fields

    private readonly ILogger _Logger;

    #endregion Fields

    public AgentInputResolver(ILogger logger)
    {
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public void PrintMainTaskUsage()
    {
        _PrintUsage();
    }

    public bool TryResolveMainTaskInputs(
        string[] args,
        string configJson,
        string runDirectory,
        string llmApiKeyFromEnvironment,
        out AgentInput agentInput)
    {
        agentInput = new AgentInput(
            "",
            "",
            60,
            "",
            "",
            2,
            2,
            "",
            "",
            "https://api.deepseek.com/v1/chat/completions",
            "deepseek-v4-flash",
            "max",
            "enabled",
            600,
            Array.Empty<string>());

        if (_ShouldShowHelp(args))
        {
            _PrintUsage();
            return false;
        }

        if (_HasUnexpectedArgs(args))
        {
            _Logger.Error(
                "Main task does not accept command-line options. Use proofagent.config.json in the current working directory.");
            _PrintUsage();
            return false;
        }

        var loader = new ProofAgentRunConfigLoader(_Logger);
        return loader.TryLoad(configJson, runDirectory, llmApiKeyFromEnvironment, out agentInput);
    }

    #region Private Methods

    private static bool _ShouldShowHelp(IReadOnlyList<string> args)
    {
        for (var i = 0; i < args.Count; i++)
        {
            if (args[i] is "-h" or "--help")
            {
                return true;
            }
        }

        return false;
    }

    private static bool _HasUnexpectedArgs(IReadOnlyList<string> args)
    {
        return args.Count > 0;
    }

    private void _PrintUsage()
    {
        _Logger.Information(
            """
            Usage:
              dotnet run --project <ProofAgent.csproj> --
              Place proofagent.config.json in the current working directory before starting.

            Configuration file (current directory):
              proofagent.config.json   Run settings (projectRoot, targetCoqFile, userMessage, checkCommand, parseSentenceScript, LLM model, etc.)

            Environment:
              LLM_API_KEY              Required OpenAI-compatible bearer token

            Optional flags:
              -h, --help                 Show this help

            Example:
              cd /path/to/run-dir
              export LLM_API_KEY='...'
              dotnet run --project /path/to/ProofAgent/ProofAgent.csproj --
            """);
    }

    #endregion Private Methods
}
