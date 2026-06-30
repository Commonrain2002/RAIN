using ProofAgent.Cli;
using Serilog;
using Xunit;

namespace ProofAgent.Tests;

public class ProofAgentRunConfigLoaderTests
{
    private const string TestLlmApiKey = "test-api-key";

    private static ProofAgentRunConfigLoader _CreateLoader()
    {
        return new ProofAgentRunConfigLoader(TestInjectedLogger.CreateFatalOnly());
    }

    private static string _MinimalValidJson(
        string? projectRoot = null,
        string targetCoqFile = "T.v",
        string userMessage = "go",
        string checkCommand = "make",
        string parseSentenceScript = "python3 ./tools/coq_sentences.py")
    {
        var projectRootLine = projectRoot == null
            ? ""
            : $"\"projectRoot\": {System.Text.Json.JsonSerializer.Serialize(projectRoot)},";
        return $$"""
            {
              {{projectRootLine}}
              "targetCoqFile": "{{targetCoqFile}}",
              "userMessage": "{{userMessage}}",
              "checkCommand": "{{checkCommand}}",
              "parseSentenceScript": "{{parseSentenceScript}}"
            }
            """;
    }

    [Fact]
    public void TryLoad_MinimalJson_ProducesAgentInput()
    {
        var runDir = Path.Combine(Path.GetTempPath(), "ProofAgentCfg_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(runDir);
        try
        {
            var loader = _CreateLoader();
            var json = _MinimalValidJson();
            Assert.True(loader.TryLoad(json, runDir, TestLlmApiKey, out var input));
            Assert.Equal(TestLlmApiKey, input.LlmApiKey, StringComparer.Ordinal);
            Assert.Equal(Path.GetFullPath(runDir), input.ProjectRoot, StringComparer.Ordinal);
            Assert.Equal("T.v", input.TargetCoqFile, StringComparer.Ordinal);
            Assert.Equal("go", input.InitialUserMessage, StringComparer.Ordinal);
            Assert.Equal(2, input.SearchHitContextLines);
            Assert.Equal(600, input.LlmHttpTimeoutSeconds);
        }
        finally
        {
            try
            {
                Directory.Delete(runDir, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }

    [Fact]
    public void TryLoad_ProjectRootRelative_ResolvesAgainstRunDirectory()
    {
        var runDir = Path.Combine(Path.GetTempPath(), "ProofAgentCfgRel_" + Guid.NewGuid().ToString("N"));
        var coqRoot = Path.Combine(runDir, "coq");
        Directory.CreateDirectory(coqRoot);
        try
        {
            var loader = _CreateLoader();
            var json = _MinimalValidJson(projectRoot: "coq");
            Assert.True(loader.TryLoad(json, runDir, TestLlmApiKey, out var input));
            Assert.Equal(Path.GetFullPath(coqRoot), input.ProjectRoot, StringComparer.Ordinal);
        }
        finally
        {
            try
            {
                Directory.Delete(runDir, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }

    [Fact]
    public void TryLoad_SearchHitContextLines_ParsesZero()
    {
        var runDir = Path.Combine(Path.GetTempPath(), "ProofAgentCfgS0_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(runDir);
        try
        {
            var loader = _CreateLoader();
            var json = _MinimalValidJson().TrimEnd('}') + ",\"searchHitContextLines\": 0}";
            Assert.True(loader.TryLoad(json, runDir, TestLlmApiKey, out var input));
            Assert.Equal(0, input.SearchHitContextLines);
        }
        finally
        {
            try
            {
                Directory.Delete(runDir, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }

    [Fact]
    public void TryLoad_ModelAndReasoningEffort_Parse()
    {
        var runDir = Path.Combine(Path.GetTempPath(), "ProofAgentCfgModel_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(runDir);
        try
        {
            var loader = _CreateLoader();
            var json = _MinimalValidJson().TrimEnd('}')
                + ",\"baseUrl\": \"https://api.example.com/v1/chat/completions\""
                + ",\"model\": \"deepseek-v4-pro\""
                + ",\"reasoningEffort\": \"High\""
                + ",\"thinking\": \"Disabled\"}";
            Assert.True(loader.TryLoad(json, runDir, TestLlmApiKey, out var input));
            Assert.Equal("https://api.example.com/v1/chat/completions", input.LlmBaseUrl, StringComparer.Ordinal);
            Assert.Equal("deepseek-v4-pro", input.ChatModel, StringComparer.Ordinal);
            Assert.Equal("high", input.ReasoningEffort, StringComparer.Ordinal);
            Assert.Equal("disabled", input.Thinking, StringComparer.Ordinal);
        }
        finally
        {
            try
            {
                Directory.Delete(runDir, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }

    [Fact]
    public void TryLoad_ExtraReadableRootPaths_DefaultEmpty()
    {
        var runDir = Path.Combine(Path.GetTempPath(), "ProofAgentCfgExtEmpty_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(runDir);
        try
        {
            var loader = _CreateLoader();
            Assert.True(loader.TryLoad(_MinimalValidJson(), runDir, TestLlmApiKey, out var input));
            Assert.Empty(input.ExtraReadableRootPaths);
        }
        finally
        {
            try
            {
                Directory.Delete(runDir, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }

    [Fact]
    public void TryLoad_ExtraReadableRootPaths_AbsolutePaths_Normalized()
    {
        var runDir = Path.Combine(Path.GetTempPath(), "ProofAgentCfgExtAbs_" + Guid.NewGuid().ToString("N"));
        var libDir = Path.Combine(runDir, "coqlib");
        Directory.CreateDirectory(libDir);
        try
        {
            var loader = _CreateLoader();
            var json = _MinimalValidJson().TrimEnd('}')
                + ",\"extraReadableRootPaths\": ["
                + System.Text.Json.JsonSerializer.Serialize(libDir)
                + "]}";
            Assert.True(loader.TryLoad(json, runDir, TestLlmApiKey, out var input));
            Assert.Single(input.ExtraReadableRootPaths);
            Assert.Equal(Path.GetFullPath(libDir), input.ExtraReadableRootPaths[0], StringComparer.Ordinal);
        }
        finally
        {
            try
            {
                Directory.Delete(runDir, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }

    [Fact]
    public void TryLoad_ExtraReadableRootPaths_RelativePath_ReturnsFalse()
    {
        var runDir = Path.Combine(Path.GetTempPath(), "ProofAgentCfgExtRel_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(runDir);
        try
        {
            var loader = _CreateLoader();
            var json = _MinimalValidJson().TrimEnd('}') + ",\"extraReadableRootPaths\": [\"coqlib\"]}";
            Assert.False(loader.TryLoad(json, runDir, TestLlmApiKey, out _));
        }
        finally
        {
            try
            {
                Directory.Delete(runDir, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }

    [Fact]
    public void TryLoad_MissingLlmApiKey_ReturnsFalse()
    {
        var loader = _CreateLoader();
        Assert.False(loader.TryLoad(_MinimalValidJson(), "/tmp", "", out _));
    }

    [Fact]
    public void TryLoad_MissingCheckCommand_ReturnsFalse()
    {
        var loader = _CreateLoader();
        var json = """
            {
              "targetCoqFile": "T.v",
              "userMessage": "go",
              "parseSentenceScript": "make"
            }
            """;
        Assert.False(loader.TryLoad(json, "/tmp", TestLlmApiKey, out _));
    }

    [Fact]
    public void TryLoad_BaseUrl_Invalid_ReturnsFalse()
    {
        var runDir = Path.Combine(Path.GetTempPath(), "ProofAgentCfgBadUrl_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(runDir);
        try
        {
            var loader = _CreateLoader();
            var json = _MinimalValidJson().TrimEnd('}') + ",\"baseUrl\": \"not-a-url\"}";
            Assert.False(loader.TryLoad(json, runDir, TestLlmApiKey, out _));
        }
        finally
        {
            try
            {
                Directory.Delete(runDir, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }

    [Fact]
    public void TryLoad_ReasoningEffort_Invalid_ReturnsFalse()
    {
        var runDir = Path.Combine(Path.GetTempPath(), "ProofAgentCfgReBad_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(runDir);
        try
        {
            var loader = _CreateLoader();
            var json = _MinimalValidJson().TrimEnd('}') + ",\"reasoningEffort\": \"ultra\"}";
            Assert.False(loader.TryLoad(json, runDir, TestLlmApiKey, out _));
        }
        finally
        {
            try
            {
                Directory.Delete(runDir, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }
}
