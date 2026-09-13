import pytest

from ssc_agent.workspace import WorkspaceManager


@pytest.fixture
def workspace(tmp_path):
    return WorkspaceManager(tmp_path / "test_workspace")


def test_workspace_initialization_creates_directory(tmp_path):
    target = tmp_path / "new_workspace_dir"
    assert not target.exists()
    wm = WorkspaceManager(target)
    assert target.exists()
    assert target.is_dir()
    assert wm.root_path == target.resolve()


def test_write_and_read_file(workspace):
    res_write = workspace.write_file("hello.txt", "Hello, World!")
    assert "Successfully wrote" in res_write
    assert "hello.txt" in res_write

    content = workspace.read_file("hello.txt")
    assert content == "Hello, World!"


def test_write_nested_file_creates_subdirectories(workspace):
    res_write = workspace.write_file("src/nested/App.cs", "class App {}")
    assert "Successfully wrote" in res_write

    content = workspace.read_file("src/nested/App.cs")
    assert content == "class App {}"


def test_read_nonexistent_file(workspace):
    content = workspace.read_file("missing.txt")
    assert "Error: File 'missing.txt' does not exist." in content


def test_list_files(workspace):
    assert "is empty" in workspace.list_files()

    workspace.write_file("file1.txt", "content1")
    workspace.write_file("sub/file2.txt", "content2")

    listing = workspace.list_files()
    assert "file1.txt" in listing
    assert "sub/file2.txt" in listing
    assert "sub/" in listing


def test_delete_file_and_directory(workspace):
    workspace.write_file("to_delete.txt", "data")
    workspace.write_file("sub/nested.txt", "nested data")

    del_file = workspace.delete_file("to_delete.txt")
    assert "Successfully deleted file 'to_delete.txt'" in del_file
    assert "Error: File 'to_delete.txt' does not exist." in workspace.read_file("to_delete.txt")

    del_dir = workspace.delete_file("sub")
    assert "Successfully deleted directory 'sub'" in del_dir
    assert "Error: File 'sub/nested.txt' does not exist." in workspace.read_file("sub/nested.txt")


def test_path_traversal_prevention(workspace):
    with pytest.raises(ValueError, match="Path traversal denied"):
        workspace._resolve_path("../outside.txt")

    with pytest.raises(ValueError, match="Path traversal denied"):
        workspace._resolve_path("../../etc/passwd")

    res_write = workspace.write_file("../outside.txt", "evil")
    assert "Error writing file" in res_write
    assert "Path traversal denied" in res_write

    res_read = workspace.read_file("../outside.txt")
    assert "Error reading file" in res_read
    assert "Path traversal denied" in res_read


def test_workspace_tools_export(workspace):
    tools = workspace.get_tools()
    tool_names = [t.name for t in tools]
    assert "write_file" in tool_names
    assert "read_file" in tool_names
    assert "list_files" in tool_names
    assert "delete_file" in tool_names

    write_tool = next(t for t in tools if t.name == "write_file")
    read_tool = next(t for t in tools if t.name == "read_file")

    res = write_tool.func(path="test.cs", content="Console.WriteLine();")
    assert "Successfully wrote" in res

    content = read_tool.func(path="test.cs")
    assert content == "Console.WriteLine();"
