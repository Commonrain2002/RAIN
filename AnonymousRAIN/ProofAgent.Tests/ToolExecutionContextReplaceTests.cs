using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

public class ToolExecutionContextReplaceTests
{
    private static string _OldTextNotFoundMessage =>
        ReflectionTestAccess.GetStaticFieldNonPublic<string>(typeof(ToolExecutionContext), "_OldTextNotFound")!;

    private static string _AmbiguousMatchMessage =>
        ReflectionTestAccess.GetStaticFieldNonPublic<string>(typeof(ToolExecutionContext), "_AmbiguousMatch")!;

    private static ToolExecutionContext CreateContext(string root)
    {
        return ToolExecutionContextTestFixtures.CreateFileOnly(root, 2);
    }

    [Fact]
    public void ReplaceBlockInFile_SingleMatchAcrossLines_ReplacesSpan()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentCtxReplace_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var filePath = Path.Combine(root, "f.txt");
            File.WriteAllLines(filePath, new[] { "a", "b", "c" });
            var ctx = CreateContext(root);
            ctx.Replace("f.txt", "b\nc", "y");
            Assert.Equal(new[] { "a", "y" }, File.ReadAllLines(filePath));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void ReplaceBlockInFile_OldTextNotFound_Throws()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentCtxReplace_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            File.WriteAllLines(Path.Combine(root, "f.txt"), new[] { "a", "b" });
            var ctx = CreateContext(root);
            var ex = Assert.Throws<InvalidOperationException>(() => ctx.Replace("f.txt", "z", "y"));
            Assert.Equal(_OldTextNotFoundMessage, ex.Message);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void ReplaceBlockInFile_AmbiguousMatch_Throws()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentCtxReplace_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            File.WriteAllText(Path.Combine(root, "f.txt"), "xxx");
            var ctx = CreateContext(root);
            var ex = Assert.Throws<InvalidOperationException>(() => ctx.Replace("f.txt", "xx", "y"));
            Assert.Equal(_AmbiguousMatchMessage, ex.Message);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void ReplaceBlockInFile_EmptyFile_Throws()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentCtxReplace_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            File.WriteAllText(Path.Combine(root, "f.txt"), string.Empty);
            var ctx = CreateContext(root);
            var ex = Assert.Throws<InvalidOperationException>(() => ctx.Replace("f.txt", "a", "b"));
            Assert.Equal(_OldTextNotFoundMessage, ex.Message);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void ReplaceBlockInFile_TwoSequentialReplaces_SecondUsesDiskAfterFirst()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentCtxReplace_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            File.WriteAllLines(Path.Combine(root, "f.txt"), new[] { "a", "b", "c" });
            var ctx = CreateContext(root);
            ctx.Replace("f.txt", "a", "A");
            Assert.Equal(new[] { "A", "b", "c" }, File.ReadAllLines(Path.Combine(root, "f.txt")));

            ctx.Replace("f.txt", "c", "C");
            Assert.Equal(new[] { "A", "b", "C" }, File.ReadAllLines(Path.Combine(root, "f.txt")));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void ReplaceBlockInFile_TwoSequentialReplaces_OnSameFileWithFourLines()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentCtxReplace_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            File.WriteAllLines(Path.Combine(root, "f.txt"), new[] { "a", "b", "c", "d" });
            var ctx = CreateContext(root);
            ctx.Replace("f.txt", "b", "B");
            ctx.Replace("f.txt", "c", "C");
            Assert.Equal(new[] { "a", "B", "C", "d" }, File.ReadAllLines(Path.Combine(root, "f.txt")));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }
}
