package tools

import (
	"fmt"
	"io/ioutil"
	"time"
)

type ListFilesTool struct{}

func (t *ListFilesTool) Name() string {
	return "list_files"
}

type FileInfo struct {
	Name    string    `json:"name"`
	Size    int64     `json:"size"`
	IsDir   bool      `json:"is_dir"`
	ModTime time.Time `json:"mod_time"`
}

func (t *ListFilesTool) Execute(args map[string]interface{}) (interface{}, error) {
	path, ok := args["path"].(string)
	if !ok {
		return nil, fmt.Errorf("missing or invalid argument 'path'")
	}

	// Basic security check: Prevent arbitrary traversal if needed,
	// but for RMM we usually want full access.
	// We might restrict to a sandbox later.

	files, err := ioutil.ReadDir(path)
	if err != nil {
		return nil, err
	}

	var result []FileInfo
	for _, f := range files {
		result = append(result, FileInfo{
			Name:    f.Name(),
			Size:    f.Size(),
			IsDir:   f.IsDir(),
			ModTime: f.ModTime(),
		})
	}

	return result, nil
}
