using Serilog;

namespace ProofAgent.Tests;

public static class TestInjectedLogger
{
    public static ILogger CreateFatalOnly()
    {
        return new LoggerConfiguration()
            .MinimumLevel.Fatal()
            .CreateLogger();
    }
}
